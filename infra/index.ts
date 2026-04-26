// Pulumi entry point. Provisions the Hetzner VPS and deploys the app stack.
// `pulumi up` from a clean slate brings up the whole thing; subsequent runs
// reconcile config / image SHA changes.
import { provisionServer } from "./server";
import { deploy } from "./deployment";

const server = provisionServer();
const app = deploy(server);

export const serverIp = server.ipv4;
export const serverName = server.name;
export const siteUrl = app.siteUrl;
