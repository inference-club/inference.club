// Pulumi entry point. Provisions the Hetzner VPS and deploys the app stack.
// `pulumi up` from a clean slate brings up the whole thing; subsequent runs
// reconcile config / image SHA changes.
import { provisionServer } from "./server";
import { provisionMediaStorage } from "./gcs";
import { deploy } from "./deployment";

const server = provisionServer();
const media = provisionMediaStorage();
const app = deploy(server, media);

export const serverIp = server.ipv4;
export const serverName = server.name;
export const siteUrl = app.siteUrl;
export const mediaPublicBucket = media.publicBucket;
export const mediaPrivateBucket = media.privateBucket;
