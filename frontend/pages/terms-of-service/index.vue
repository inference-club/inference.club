<script setup lang="ts">
definePageMeta({
  layout: 'default',
  title: 'Terms of Service',
  description: 'Terms of Service for inference.club',
})
</script>

<template>
  <div class="container mx-auto px-4 sm:px-6 lg:px-8 py-8 max-w-4xl">
    <h1 class="text-3xl font-bold mb-2">Terms of Service</h1>
    <p class="text-sm text-muted-foreground mb-8">Last updated: May 29, 2026</p>

    <p class="mb-6">
      These Terms of Service ("Terms") govern your access to and use of Inference Club's website, services, APIs, and applications (collectively, the "Service"). By accessing or using the Service, you agree to be bound by these Terms.
    </p>

    <!-- Prominent up-front summary of the most important risks. -->
    <div class="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 mb-8 text-sm space-y-2">
      <p class="font-semibold">Please read this first:</p>
      <ul class="list-disc pl-5 space-y-1.5">
        <li>
          <strong>This is an experimental product.</strong> inference.club is an
          early-stage, experimental project provided on a best-effort basis. It may be
          unreliable, change, or lose data at any time, and it is not intended for
          production or mission-critical use.
        </li>
        <li>
          <strong>Do not share sensitive information.</strong> Do not submit personal,
          confidential, proprietary, regulated, or otherwise sensitive information in
          your prompts, inputs, or other Content.
        </li>
        <li>
          <strong>Your data is open by default.</strong> Unless stated otherwise, your
          prompts, generated outputs, and related metadata are public by default and
          may be viewed by other inference.club members and by anyone on the internet.
        </li>
        <li>
          <strong>Inference runs on other people's computers.</strong> When you use a
          Provider's compute, your prompts and outputs are processed on hardware
          operated by other members and may be accessible to those operators and other
          members of the network. Content others generate using your compute may
          likewise be available to you.
        </li>
      </ul>
    </div>

    <div class="space-y-8">
      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">1. Definitions</h2>
        <ul class="list-disc pl-6 space-y-2">
          <li><strong>Platform:</strong> inference.club and all related domains and subdomains.</li>
          <li><strong>User:</strong> any individual or entity that accesses or uses the Service.</li>
          <li><strong>Provider:</strong> a User who offers compute resources or AI models for inference.</li>
          <li><strong>Requester:</strong> a User who submits inference jobs to the Platform.</li>
          <li><strong>Content:</strong> any data, text, image, audio, code, model, or other material uploaded or submitted by Users.</li>
        </ul>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">2. Acceptance of Terms</h2>
        <p>By registering for, accessing, or using the Service, you accept and agree to these Terms and our Privacy Policy. If you do not agree, you may not use the Service.</p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">3. Changes to Terms</h2>
        <p>Inference Club may modify these Terms at any time. We will post updated Terms with a revised "Last Updated" date. Continued use of the Service after any changes constitutes acceptance of the new Terms.</p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">4. Eligibility</h2>
        <p>You must be at least 18 years old (or the legal age of majority in your jurisdiction) and capable of entering into binding contracts to use the Service. By registering, you represent and warrant that you meet these requirements.</p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">5. Account Registration</h2>
        <ul class="list-disc pl-6 space-y-2">
          <li>You agree to provide accurate, current, and complete information.</li>
          <li>You are responsible for safeguarding your password and account.</li>
          <li>You agree to notify us immediately of any unauthorized use.</li>
        </ul>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">6. Use of the Service</h2>
        <ul class="list-disc pl-6 space-y-2">
          <li>Requesters may submit jobs, supply prompts, and receive inference results.</li>
          <li>Providers may register compute resources, install the Inference Club Agent, and accept jobs.</li>
          <li>You agree to use the Service only for lawful purposes and in accordance with these Terms.</li>
        </ul>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">7. Payments and Credits</h2>
        <ul class="list-disc pl-6 space-y-2">
          <li>Access to inference requires credits. Credits may be purchased or earned by providing compute.</li>
          <li>All fees are non-refundable except as required by law.</li>
          <li>We reserve the right to modify pricing or introduce new fees.</li>
        </ul>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">8. User Content, Public Data, and Sensitive Information</h2>
        <ul class="list-disc pl-6 space-y-2">
          <li>You retain all rights to Content you upload. You grant Inference Club a worldwide, royalty-free license to host, store, distribute, and display your Content to provide and operate the Service.</li>
          <li><strong>Public by default.</strong> Unless we expressly state otherwise, the Content you submit (including prompts and generated outputs) and related metadata (such as model and provider names, timestamps, token counts, and status) are open by default and may be displayed to other Users and to the general public, including anyone on the internet.</li>
          <li><strong>Processing on third-party hardware.</strong> Inference may be performed on compute operated by other Users ("Providers"). Your Content may be transmitted to, processed on, stored by, and accessible to those Providers and other members of the network. We do not control, and are not responsible for, how Providers or other members handle Content on their own systems.</li>
          <li><strong>No sensitive information.</strong> You must not submit confidential, personal, proprietary, regulated, or otherwise sensitive information through the Service. You assume all risk arising from any Content you submit.</li>
          <li>You are solely responsible for your Content and any consequences of submitting it.</li>
        </ul>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">9. Prohibited Conduct</h2>
        <p class="mb-2">You agree not to:</p>
        <ul class="list-disc pl-6 space-y-2">
          <li>Violate any laws or regulations.</li>
          <li>Infringe intellectual property rights.</li>
          <li>Transmit malware or harmful code.</li>
          <li>Interfere with the Service's security or operation.</li>
          <li>Use the Service to generate unlawful or harmful content.</li>
        </ul>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">10. Intellectual Property</h2>
        <p>All rights, title, and interest in the Platform (excluding User Content) are owned by Inference Club or its licensors. The Service is protected by copyright, trademark, and other laws.</p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">11. Disclaimers</h2>
        <p class="mb-3">The Service is experimental and is offered on a best-effort basis. Features may change, break, or be discontinued, and Content may be lost, corrupted, exposed, or made public, at any time and without notice. You should not rely on the Service for any important, time-sensitive, or production use, and you should keep your own copies of anything you care about.</p>
        <p class="italic">THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND. INFERENCE CLUB DISCLAIMS ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT.</p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">12. Limitation of Liability</h2>
        <p class="italic">TO THE MAXIMUM EXTENT PERMITTED BY LAW, INFERENCE CLUB WILL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, OR CONSEQUENTIAL DAMAGES ARISING FROM OR RELATED TO YOUR USE OF THE SERVICE.</p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">13. Indemnification</h2>
        <p>You agree to indemnify and hold Inference Club and its officers, directors, employees, and agents harmless from any claim, demand, loss, liability, or expense arising out of your use of the Service or breach of these Terms.</p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">14. Termination</h2>
        <p>We may suspend or terminate your access at any time, with or without cause. Upon termination, your rights under these Terms will immediately cease.</p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">15. Governing Law</h2>
        <p>These Terms are governed by and construed in accordance with the laws of the State of New York, without regard to conflict of laws principles.</p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">16. Severability</h2>
        <p>If any provision of these Terms is held invalid, the remainder will continue in full force and effect.</p>
      </section>

      <section class="border-b pb-6 mb-6">
        <h2 class="text-2xl font-semibold mb-4">17. Entire Agreement</h2>
        <p>These Terms, together with the Privacy Policy, constitute the entire agreement between you and Inference Club regarding the Service.</p>
      </section>

      <section class="pb-6">
        <h2 class="text-2xl font-semibold mb-4">18. Contact</h2>
        <p>If you have questions or concerns about these Terms, please contact us at <a href="mailto:support@inference.club" class="text-blue-600 hover:underline">support@inference.club</a>.</p>
      </section>
    </div>
  </div>
</template>