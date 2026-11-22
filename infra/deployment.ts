import * as command from "@pulumi/command";
import * as fs from "fs";
import * as path from "path";
import type { Server } from "./server";

// Node-level setup, run over SSH. Pulumi's job ends at "a hardened server
// running k3s with Argo CD bootstrapped". Everything that runs *on* the
// cluster (ingress config aside) is deployed by Argo CD from k8s/ in this
// repo, so application deploys never go through Pulumi.

function loadScript(name: string): string {
    return fs.readFileSync(path.join(__dirname, "templates", name), "utf8");
}

// Ship a script as base64 and run it. Scripts are idempotent and re-run
// whenever their contents change.
function runScript(
    name: string,
    script: string,
    conn: command.types.input.remote.ConnectionArgs,
    dependsOn: command.remote.Command[] = [],
): command.remote.Command {
    const b64 = Buffer.from(script, "utf8").toString("base64");
    return new command.remote.Command(name, {
        connection: conn,
        create: `printf '%s' '${b64}' | base64 -d | bash`,
        triggers: [script],
    }, { dependsOn });
}

export function deploy(server: Server): void {
    const conn: command.types.input.remote.ConnectionArgs = {
        host: server.ipv4,
        user: "root",
        privateKey: server.sshPrivateKey,
    };

    // Key-only sshd, fail2ban and the ufw host firewall.
    const harden = runScript("harden-host", loadScript("harden.sh"), conn);

    // Pinned k3s, Traefik config, one-time Argo CD bootstrap. Runs after the
    // firewall rules that let pods reach the node are in place.
    runScript("k3s", loadScript("k3s.sh"), conn, [harden]);
}
