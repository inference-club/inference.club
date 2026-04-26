import * as pulumi from "@pulumi/pulumi";

// Single source of truth for stack config. All Pulumi config keys are read here
// so the rest of the program reads typed values, not stringly-typed lookups.
const cfg = new pulumi.Config();

export const stackConfig = {
    domain: cfg.get("domain") ?? "inference.club",
    hcloudLocation: cfg.get("hcloudLocation") ?? "nbg1",
    serverType: cfg.get("serverType") ?? "cx22",

    backendImage: cfg.require("backendImage"),
    frontendImage: cfg.require("frontendImage"),

    // Secrets — set with `pulumi config set --secret <key> <value>`.
    hcloudToken: cfg.requireSecret("hcloudToken"),
    sshPublicKey: cfg.requireSecret("sshPublicKey"),
    sshPrivateKey: cfg.requireSecret("sshPrivateKey"),

    djangoSecretKey: cfg.requireSecret("djangoSecretKey"),
    postgresPassword: cfg.requireSecret("postgresPassword"),

    githubOauthClientId: cfg.requireSecret("githubOauthClientId"),
    githubOauthClientSecret: cfg.requireSecret("githubOauthClientSecret"),

    // Read-only token used on the server to `docker login ghcr.io` and pull
    // private images. A classic GitHub PAT with `read:packages` scope.
    ghcrUsername: cfg.requireSecret("ghcrUsername"),
    ghcrToken: cfg.requireSecret("ghcrToken"),
};

export type StackConfig = typeof stackConfig;
