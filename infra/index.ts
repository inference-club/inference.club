// Pulumi entry point. Provisions the Hetzner VPS, hardens it and installs
// k3s + Argo CD. The application itself is deployed by Argo CD from k8s/.
import { stackConfig } from "./config";
import { provisionServer } from "./server";
import { provisionMediaStorage } from "./gcs";
import { deploy } from "./deployment";

const server = provisionServer();
const media = provisionMediaStorage();
deploy(server);

export const serverIp = server.ipv4;
export const serverName = server.name;
export const siteUrl = `https://${stackConfig.domain}`;
export const mediaPublicBucket = media.publicBucket;
export const mediaPrivateBucket = media.privateBucket;
