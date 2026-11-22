import * as hcloud from "@pulumi/hcloud";
import * as pulumi from "@pulumi/pulumi";
import { stackConfig } from "./config";

// cloud-init script that runs once when a server first boots. Only brings
// packages up to date; k3s and the firewall are installed afterwards by the
// scripts in deployment.ts, which can be re-run (cloud-init cannot).
const cloudInit = `#cloud-config
package_update: true
package_upgrade: true
packages:
  - ca-certificates
  - curl
`;

export interface Server {
    ipv4: pulumi.Output<string>;
    name: pulumi.Output<string>;
    sshPrivateKey: pulumi.Output<string>;
}

export function provisionServer(): Server {
    const sshKey = new hcloud.SshKey(
        "inference-club",
        {
            name: "inference-club-deploy",
            publicKey: stackConfig.sshPublicKey,
        },
        // Hetzner SSH key names must be globally unique within the project, so
        // when Pulumi wants to replace the key we have to delete the old one
        // first to free the name.
        { deleteBeforeReplace: true },
    );

    // Allow SSH (auth via the keypair above), HTTP, and HTTPS. Everything
    // else is dropped at the cloud edge, including the Kubernetes API (6443):
    // reach that over an SSH tunnel.
    const firewall = new hcloud.Firewall("inference-club", {
        name: "inference-club",
        rules: [
            { direction: "in", protocol: "tcp", port: "22", sourceIps: ["0.0.0.0/0", "::/0"] },
            { direction: "in", protocol: "tcp", port: "80", sourceIps: ["0.0.0.0/0", "::/0"] },
            { direction: "in", protocol: "tcp", port: "443", sourceIps: ["0.0.0.0/0", "::/0"] },
        ],
    });

    const server = new hcloud.Server("inference-club", {
        name: "inference-club",
        serverType: stackConfig.serverType,
        location: stackConfig.hcloudLocation,
        image: "debian-12",
        sshKeys: [sshKey.id],
        firewallIds: [firewall.id.apply((id) => parseInt(id, 10))],
        userData: cloudInit,
        // Resizes change CPU and RAM only. Leaving the disk alone keeps the
        // option of sizing back down.
        keepDisk: true,
        // Hetzner refuses to delete or rebuild the server while these are
        // on. The server holds the database, and its server type can be out
        // of stock, so a replacement might not be obtainable.
        deleteProtection: true,
        rebuildProtection: true,
    }, {
        // Changing userData would replace (destroy and recreate) the server.
        // cloud-init only matters for a brand-new server anyway.
        ignoreChanges: ["userData"],
        protect: true,
    });

    return {
        ipv4: server.ipv4Address,
        name: server.name,
        sshPrivateKey: stackConfig.sshPrivateKey,
    };
}
