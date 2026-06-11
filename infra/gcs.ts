import * as gcp from "@pulumi/gcp";
import * as pulumi from "@pulumi/pulumi";
import { stackConfig } from "./config";

// Media storage on Google Cloud Storage. Two buckets so the IAM story stays
// dead simple under uniform bucket-level access (no per-object ACLs):
//
//   <project>-media-public  : generated output (images/audio/video/3D) plus
//                             input images. World-readable; browsers fetch
//                             straight from storage.googleapis.com instead of
//                             streaming every byte through Django on the VPS.
//                             Object keys embed a UUID (see
//                             media_asset_upload_to) so URLs are unguessable.
//   <project>-media-private : owner-gated STT input audio. Public access
//                             prevention enforced; only the media service
//                             account can read, and the backend streams it
//                             through its authenticated asset route.
//
// The backend authenticates as a dedicated service account that can touch
// objects in these two buckets and nothing else in the project. Its key
// travels to the VPS inside backend.env (GCS_CREDENTIALS_B64).
//
// No Cloud CDN yet: that needs an external HTTPS load balancer (~$18/mo fixed
// + a managed cert, which needs a real hostname). Direct GCS serving already
// terminates on Google's edge network and costs only storage + egress. When
// we want cdn.<domain>, add a backend-bucket + LB here and point the
// backend's GCS_PUBLIC_CUSTOM_ENDPOINT at it.

export interface MediaStorage {
    publicBucket: pulumi.Output<string>;
    privateBucket: pulumi.Output<string>;
    /** Service-account key JSON, base64-encoded (as GCP emits it). */
    credentialsB64: pulumi.Output<string>;
}

export function provisionMediaStorage(): MediaStorage {
    const project = new pulumi.Config("gcp").require("project");

    // Browsers fetch some public assets with XHR/fetch (music visualizer
    // decodes audio, <model-viewer> loads GLBs), so the bucket must answer
    // CORS preflights from the site origins. Plain <img>/<video> tags don't
    // need this, but it costs nothing to cover them too.
    const corsOrigins = pulumi
        .output(stackConfig.domain)
        .apply((d) => [
            `https://${d}`,
            `https://www.${d}`,
            "http://localhost:3000",
            "http://localhost:3001",
        ]);

    // retainOnDelete: an `infra-destroy` rebuilds the VPS from scratch by
    // design (it's cattle), but media is user data — a destroy must never
    // take the buckets with it. Orphaned buckets can be re-imported or
    // cleaned up by hand.
    const publicBucket = new gcp.storage.Bucket(
        "media-public",
        {
            name: `${project}-media-public`,
            location: stackConfig.gcsLocation,
            uniformBucketLevelAccess: true,
            publicAccessPrevention: "inherited",
            cors: [
                {
                    origins: corsOrigins,
                    methods: ["GET", "HEAD"],
                    responseHeaders: ["Content-Type", "Range"],
                    maxAgeSeconds: 3600,
                },
            ],
        },
        { retainOnDelete: true },
    );

    new gcp.storage.BucketIAMMember("media-public-all-users", {
        bucket: publicBucket.name,
        role: "roles/storage.objectViewer",
        member: "allUsers",
    });

    const privateBucket = new gcp.storage.Bucket(
        "media-private",
        {
            name: `${project}-media-private`,
            location: stackConfig.gcsLocation,
            uniformBucketLevelAccess: true,
            publicAccessPrevention: "enforced",
        },
        { retainOnDelete: true },
    );

    const mediaSa = new gcp.serviceaccount.Account("media-storage", {
        accountId: "media-storage",
        displayName: "inference.club backend media storage",
        description:
            "Object read/write on the media buckets only; used by Django " +
            "(django-storages) and the one-off MinIO->GCS migration.",
    });

    for (const [label, bucket] of [
        ["public", publicBucket],
        ["private", privateBucket],
    ] as const) {
        new gcp.storage.BucketIAMMember(`media-sa-${label}-object-admin`, {
            bucket: bucket.name,
            role: "roles/storage.objectAdmin",
            member: pulumi.interpolate`serviceAccount:${mediaSa.email}`,
        });
    }

    const mediaSaKey = new gcp.serviceaccount.Key("media-storage-key", {
        serviceAccountId: mediaSa.name,
    });

    return {
        publicBucket: publicBucket.name,
        privateBucket: privateBucket.name,
        // gcp.serviceaccount.Key.privateKey is already base64-encoded JSON —
        // exactly the single-line shape backend.env needs.
        credentialsB64: pulumi.secret(mediaSaKey.privateKey),
    };
}
