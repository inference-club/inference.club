import * as pulumi from "@pulumi/pulumi";

// All Pulumi config the program needs, read in one place so the rest of the
// code is typed.
//
// User-supplied:
//   - HCLOUD_TOKEN env var : Hetzner Cloud API token; consumed directly by the
//                            hcloud provider, not via Pulumi config
//   - sshPublicKey         : OpenSSH public key registered with Hetzner
//   - DEPLOY_SSH_PRIVATE_KEY env var : matching private key (base64), used to
//                            run the node setup scripts over SSH
//
// Application secrets are NOT here any more: they live as SealedSecrets in
// k8s/inference-club/secrets and are decrypted inside the cluster.
const cfg = new pulumi.Config();

export const stackConfig = {
    domain: cfg.get("domain") ?? "inference.club",
    hcloudLocation: cfg.get("hcloudLocation") ?? "nbg1",
    serverType: cfg.get("serverType") ?? "cx33",

    // GCS media buckets live next to the Hetzner box (nbg1 = Nuremberg, so
    // europe-west3 = Frankfurt) to keep backend<->bucket latency low. The GCP
    // project itself comes from the `gcp:project` provider config.
    gcsLocation: cfg.get("gcsLocation") ?? "EUROPE-WEST3",

    sshPublicKey: cfg.requireSecret("sshPublicKey"),

    // The SSH private key comes in via env (DEPLOY_SSH_PRIVATE_KEY) rather
    // than Pulumi config, because pulumi/actions's config-map is YAML and
    // can't carry multi-line values cleanly. The repo secret holds the key
    // base64-encoded so it travels as a single line through workflow env;
    // we decode here.
    sshPrivateKey: pulumi.secret(
        (() => {
            const b64 = process.env.DEPLOY_SSH_PRIVATE_KEY;
            if (!b64) {
                throw new Error(
                    "DEPLOY_SSH_PRIVATE_KEY env var is missing. Set the " +
                        "repo secret of the same name (base64-encoded PEM).",
                );
            }
            return Buffer.from(b64, "base64").toString("utf8");
        })(),
    ),
};

export type StackConfig = typeof stackConfig;
