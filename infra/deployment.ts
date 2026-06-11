import * as command from "@pulumi/command";
import * as pulumi from "@pulumi/pulumi";
import * as random from "@pulumi/random";
import * as fs from "fs";
import * as path from "path";
import { stackConfig } from "./config";
import type { Server } from "./server";
import type { MediaStorage } from "./gcs";

const REMOTE_DIR = "/srv/inference-club";

// Read a template once per program run. Templates use __TOKEN__ placeholders
// so we don't pull in a templating library; substitution is a few small
// string.replace calls below.
function loadTemplate(name: string): string {
    return fs.readFileSync(path.join(__dirname, "templates", name), "utf8");
}

// Substitute __TOKEN__ placeholders. All values are pulumi.Outputs so we
// resolve them with pulumi.all() and produce one Output<string>.
function render(
    template: string,
    substitutions: Record<string, pulumi.Input<string>>,
): pulumi.Output<string> {
    return pulumi.all(substitutions).apply((resolved) => {
        let out = template;
        for (const [key, value] of Object.entries(resolved)) {
            out = out.split(`__${key}__`).join(String(value));
        }
        return out;
    });
}

export function deploy(
    server: Server,
    media: MediaStorage,
): { siteUrl: pulumi.Output<string> } {
    // Auto-generated app secrets. Pulumi state persists these across runs so
    // a re-deploy doesn't regenerate them (which would invalidate sessions
    // and break the existing Postgres data dir).
    const djangoSecretKey = new random.RandomPassword("django-secret-key", {
        length: 64,
        special: false,
    });
    const postgresPassword = new random.RandomPassword("postgres-password", {
        length: 32,
        // Avoid characters that need shell-escaping inside the .env file we
        // ship to the VPS.
        overrideSpecial: "_-",
        special: true,
    });
    // Credentials for the self-hosted MinIO (S3-compatible object storage) that
    // holds media: STT input audio now, TTS/image output later. Same escaping
    // constraint as the Postgres password (lands in backend.env).
    const minioPassword = new random.RandomPassword("minio-password", {
        length: 32,
        overrideSpecial: "_-",
        special: true,
    });

    const conn: command.types.input.remote.ConnectionArgs = {
        host: server.ipv4,
        user: "root",
        privateKey: server.sshPrivateKey,
    };

    // Wait for cloud-init to finish (Docker installed + /srv/inference-club
    // created) before we try to ship files. Polls every 5s for up to 5 min.
    const cloudInitWait = new command.remote.Command("wait-for-cloud-init", {
        connection: conn,
        create:
            "for i in $(seq 1 60); do " +
            " if command -v docker >/dev/null && [ -d /srv/inference-club ]; then exit 0; fi; " +
            " sleep 5; " +
            "done; echo 'cloud-init did not finish in time' >&2; exit 1",
    });

    // ---- render config files ----------------------------------------------

    const composeYaml = render(loadTemplate("docker-compose.yml.tpl"), {
        BACKEND_IMAGE: stackConfig.backendImage,
        FRONTEND_IMAGE: stackConfig.frontendImage,
        POSTGRES_PASSWORD: postgresPassword.result,
        MINIO_ROOT_PASSWORD: minioPassword.result,
        DOMAIN: stackConfig.domain,
        TAILSCALE_WEB_AUTHKEY: stackConfig.tailscaleWebAuthkey,
    });

    const caddyfile = render(loadTemplate("Caddyfile.tpl"), {
        DOMAIN: stackConfig.domain,
    });

    const backendEnv = render(loadTemplate("backend.env.tpl"), {
        DJANGO_SECRET_KEY: djangoSecretKey.result,
        POSTGRES_PASSWORD: postgresPassword.result,
        GITHUB_OAUTH_CLIENT_ID: stackConfig.githubOauthClientId,
        GITHUB_OAUTH_CLIENT_SECRET: stackConfig.githubOauthClientSecret,
        TAILSCALE_TAILNET: stackConfig.tailscaleTailnet,
        TAILSCALE_STATIC_AUTHKEY: stackConfig.tailscaleStaticAuthkey,
        MINIO_ROOT_PASSWORD: minioPassword.result,
        DOMAIN: stackConfig.domain,
        GCS_PUBLIC_BUCKET: media.publicBucket,
        GCS_PRIVATE_BUCKET: media.privateBucket,
        GCS_CREDENTIALS_B64: media.credentialsB64,
    });

    // ---- ship files via SSH heredocs --------------------------------------
    // CopyToRemote needs a local source file; using base64-piped-into-base64-d
    // keeps secrets in Pulumi state only and avoids touching the local fs.

    function shipFile(
        name: string,
        contents: pulumi.Output<string>,
        dependsOn: pulumi.Resource[],
        mode = "0644",
    ): command.remote.Command {
        return new command.remote.Command(`ship-${name}`, {
            connection: conn,
            create: contents.apply((c) => {
                const b64 = Buffer.from(c, "utf8").toString("base64");
                return `printf '%s' '${b64}' | base64 -d > ${REMOTE_DIR}/${name} && chmod ${mode} ${REMOTE_DIR}/${name}`;
            }),
            // Re-ship whenever the contents change.
            triggers: [contents],
        }, { dependsOn });
    }

    const composeFile = shipFile("docker-compose.yml", composeYaml, [cloudInitWait]);
    const caddyFile = shipFile("Caddyfile", caddyfile, [cloudInitWait]);
    const envFile = shipFile("backend.env", backendEnv, [cloudInitWait], "0600");

    // ---- ghcr login + compose up ------------------------------------------

    const ghcrLogin = new command.remote.Command("ghcr-login", {
        connection: conn,
        create: pulumi
            .all([stackConfig.ghcrUsername, stackConfig.ghcrToken])
            .apply(([u, t]) =>
                `echo ${t} | docker login ghcr.io -u ${u} --password-stdin`,
            ),
        triggers: [stackConfig.ghcrToken],
    }, { dependsOn: [cloudInitWait] });

    const composeUp = new command.remote.Command("compose-up", {
        connection: conn,
        create:
            `cd ${REMOTE_DIR} && ` +
            "docker compose pull && " +
            "docker compose up -d --remove-orphans",
        // Re-run when any of these inputs change so a new image SHA actually
        // gets pulled and rolled out.
        triggers: [
            stackConfig.backendImage,
            stackConfig.frontendImage,
            composeYaml,
            caddyfile,
            backendEnv,
        ],
    }, {
        dependsOn: [composeFile, caddyFile, envFile, ghcrLogin],
    });

    return {
        siteUrl: pulumi.interpolate`https://${stackConfig.domain}`,
    };
}
