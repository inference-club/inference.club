import * as hcloud from "@pulumi/hcloud";
import * as pulumi from "@pulumi/pulumi";
import { stackConfig } from "./config";

// cloud-init script that runs once when the VPS first boots. Installs Docker
// + the compose plugin and pre-creates /srv/inference-club so the deployment
// step can scp files into it as root.
const cloudInit = `#cloud-config
package_update: true
package_upgrade: true
packages:
  - ca-certificates
  - curl
  - gnupg
runcmd:
  - install -m 0755 -d /etc/apt/keyrings
  - curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  - chmod a+r /etc/apt/keyrings/docker.asc
  - |
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
  - apt-get update
  - apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  - install -d -m 0755 /srv/inference-club
  - install -d -m 0755 /srv/inference-club/caddy-data
  - install -d -m 0755 /srv/inference-club/caddy-config
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
    // else is dropped at the cloud edge.
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
    });

    return {
        ipv4: server.ipv4Address,
        name: server.name,
        sshPrivateKey: stackConfig.sshPrivateKey,
    };
}
