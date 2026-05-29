<script setup lang="ts">
definePageMeta({
  layout: 'default',
  title: 'Privacy Policy',
  description: 'Privacy Policy for inference.club',
})
</script>

<template>
  <div class="container mx-auto px-4 sm:px-6 lg:px-8 py-8 max-w-4xl">
    <h1 class="text-3xl font-bold mb-2">Privacy Policy</h1>
    <p class="text-sm text-muted-foreground mb-8">Last updated: May 29, 2026</p>

    <p class="mb-6">
      This Privacy Policy explains how Inference Club ("we", "us", or "the Service") handles
      information in connection with inference.club and related domains, applications, and APIs.
      By using the Service, you agree to the practices described here and in our
      <NuxtLink to="/terms-of-service" class="text-blue-600 hover:underline">Terms of Service</NuxtLink>.
    </p>

    <!-- Prominent up-front summary of the most important privacy facts. -->
    <div class="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 mb-8 text-sm space-y-2">
      <p class="font-semibold">The most important things to know:</p>
      <ul class="list-disc pl-5 space-y-1.5">
        <li>
          <strong>This is an experimental product.</strong> Treat anything you do here as
          public and impermanent. Do not rely on the Service to keep your data private,
          available, or intact.
        </li>
        <li>
          <strong>Your data is open by default.</strong> Your prompts, generated outputs, and
          related metadata are public by default and may be viewable by other members and by
          anyone on the internet.
        </li>
        <li>
          <strong>Inference runs on other members' computers.</strong> Content you generate may
          be processed on hardware operated by other members and be accessible to them; content
          others generate using your hardware may be accessible to you.
        </li>
        <li>
          <strong>Do not share sensitive information.</strong> Never submit personal,
          confidential, proprietary, regulated, or otherwise sensitive information.
        </li>
      </ul>
    </div>

    <div class="space-y-8">
      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">1. Information We Collect</h2>
        <ul class="list-disc pl-6 space-y-2">
          <li><strong>Account information.</strong> When you sign in with GitHub, we receive your GitHub username and associated email address, and store a basic account record.</li>
          <li><strong>Inference content.</strong> The prompts and inputs you submit, the outputs generated for you, and related metadata (model name, provider, timestamps, token counts, latency, status, and any reasoning traces).</li>
          <li><strong>Provider information.</strong> If you operate a node, the details you publish in your service manifest (such as host descriptions, hardware, and the models you serve).</li>
          <li><strong>Technical data.</strong> Basic logs and request data generated when you use the Service.</li>
        </ul>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">2. How We Use Information</h2>
        <ul class="list-disc pl-6 space-y-2">
          <li>To operate, provide, and improve the Service, including routing inference requests to Providers.</li>
          <li>To display your activity, content, and provider information within the Service as described below.</li>
          <li>To maintain security, prevent abuse, and debug and develop the Service.</li>
        </ul>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">3. Public and Open Data</h2>
        <p class="mb-2">
          inference.club is designed around an open, transparent network. <strong>Unless we expressly
          state otherwise, the following are public by default:</strong>
        </p>
        <ul class="list-disc pl-6 space-y-2">
          <li>Your prompts, inputs, and the outputs generated for you (including reasoning traces).</li>
          <li>Request metadata such as model and provider names, timestamps, token counts, status, and latency.</li>
          <li>Your public profile, GitHub handle, and any provider/manifest information you publish.</li>
        </ul>
        <p class="mt-3">
          "Public by default" means this information may be viewed by other signed-in members and,
          in many cases, by anyone on the internet — including content you generate using your own
          or other people's inference services. Do not put anything here that you would not be
          comfortable making public.
        </p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">4. Processing on Third-Party (Member) Hardware</h2>
        <p>
          Inference is performed on compute operated by other members ("Providers"), not by us. When
          you submit a request, your prompt and the resulting output are transmitted to, processed on,
          and may be stored by a Provider's hardware, where they may be accessible to that Provider's
          operator and to other members of the network. We do not control, and are not responsible for,
          how Providers or other members store, log, retain, or use Content on their own systems. If you
          operate a Provider, you may have access to Content that other members generate using your
          hardware, and you agree to handle it responsibly and lawfully.
        </p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">5. No Sensitive Information</h2>
        <p>
          Because the Service is experimental and much of its data is open by default and processed on
          third-party hardware, you must not submit confidential, personal, proprietary, regulated
          (e.g., health, financial, or government-issued identifiers), or otherwise sensitive
          information. You are solely responsible for the Content you submit and assume all associated risk.
        </p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">6. How Information Is Shared</h2>
        <ul class="list-disc pl-6 space-y-2">
          <li><strong>With other members and the public</strong>, as described in "Public and Open Data" above.</li>
          <li><strong>With Providers</strong>, to fulfill inference requests, as described above.</li>
          <li><strong>With service providers</strong> that help us operate the Service (such as hosting and authentication).</li>
          <li><strong>For legal reasons</strong>, where required by law or to protect the rights, safety, or property of users or the public.</li>
        </ul>
        <p class="mt-3">We do not sell your personal information.</p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">7. Data Retention and Deletion</h2>
        <p>
          We retain account and inference data for as long as needed to operate the Service. You can
          delete your own inference requests from your dashboard. Note that deletion from inference.club
          does not guarantee deletion of any copies, logs, or caches that Providers or other parties may
          have created on their own systems, and that public content may have been viewed, copied, or
          indexed by others before deletion.
        </p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">8. Security</h2>
        <p>
          We make reasonable, best-effort attempts to protect the Service, but it is experimental and
          provided "as is". We cannot guarantee the security, confidentiality, availability, or
          integrity of any data, and you use the Service at your own risk.
        </p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">9. Children</h2>
        <p>
          The Service is not directed to, and may not be used by, anyone under 18 years of age (or the
          age of majority in your jurisdiction). We do not knowingly collect information from children.
        </p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">10. Your Choices</h2>
        <ul class="list-disc pl-6 space-y-2">
          <li>You can delete your inference requests, and you can stop using the Service at any time.</li>
          <li>You can choose not to submit any particular prompt or Content.</li>
          <li>To request account deletion or ask about your data, contact us using the details below.</li>
        </ul>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">11. Changes to This Policy</h2>
        <p>
          We may update this Privacy Policy from time to time. We will post the updated version with a
          revised "Last updated" date. Your continued use of the Service after changes take effect
          constitutes acceptance of the updated policy.
        </p>
      </section>

      <section class="pb-6">
        <h2 class="text-2xl font-semibold mb-4">12. Contact</h2>
        <p>
          If you have questions about this Privacy Policy, please contact us at
          <a href="mailto:support@inference.club" class="text-blue-600 hover:underline">support@inference.club</a>.
        </p>
      </section>
    </div>
  </div>
</template>
