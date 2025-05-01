<template>
  <div>
    <!-- Hero Section -->
    <section class="relative py-20 px-4 sm:px-6 lg:px-8 bg-gradient-to-b from-background to-muted">
      <div class="max-w-7xl mx-auto">
        <div class="text-center">
          <h1 class="text-4xl sm:text-5xl md:text-6xl font-bold tracking-tight text-foreground">
            welcome to <span class="text-primary"><strong>inference.club</strong></span>
          </h1>
          <p class="mt-6 text-xl text-muted-foreground max-w-3xl mx-auto">
            Join a community of AI enthusiasts, researchers, and practitioners. Learn, share, and grow together in the world of artificial intelligence.
          </p>
          <div class="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
            <Button size="lg" class="w-full sm:w-auto">
              Join the Club
              <ArrowRight class="ml-2 h-4 w-4" />
            </Button>
            <Button size="lg" variant="outline" class="w-full sm:w-auto">
              Learn More
            </Button>
          </div>
        </div>
      </div>
    </section>

    <!-- Features Section -->
    <section class="py-20 px-4 sm:px-6 lg:px-8">
      <div class="max-w-7xl mx-auto">
        <h2 class="text-3xl font-bold text-center mb-12">Why Join Inference.Club?</h2>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
          <Card class="p-6">
            <CardHeader>
              <CardTitle>Learn from Experts</CardTitle>
            </CardHeader>
            <CardContent>
              <p class="text-muted-foreground">
                Access exclusive content and learn from industry leaders and researchers in the field of AI.
              </p>
            </CardContent>
          </Card>

          <Card class="p-6">
            <CardHeader>
              <CardTitle>Community Projects</CardTitle>
            </CardHeader>
            <CardContent>
              <p class="text-muted-foreground">
                Collaborate on exciting AI projects and contribute to the advancement of the field.
              </p>
            </CardContent>
          </Card>

          <Card class="p-6">
            <CardHeader>
              <CardTitle>Networking</CardTitle>
            </CardHeader>
            <CardContent>
              <p class="text-muted-foreground">
                Connect with like-minded individuals and expand your professional network.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>

    <!-- Testimonials Section -->
    <section class="py-20 px-4 sm:px-6 lg:px-8 bg-muted">
      <div class="max-w-7xl mx-auto">
        <h2 class="text-3xl font-bold text-center mb-12">What Our Members Say</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          <Card class="p-6">
            <CardContent>
              <div class="flex items-center gap-4 mb-4">
                <Avatar>
                  <AvatarImage src="/avatars/1.png" alt="Sarah" />
                  <AvatarFallback>SA</AvatarFallback>
                </Avatar>
                <div>
                  <p class="font-semibold">Sarah Anderson</p>
                  <p class="text-sm text-muted-foreground">AI Researcher</p>
                </div>
              </div>
              <p class="text-muted-foreground">
                "Inference.Club has been instrumental in my AI research journey. The community is incredibly supportive and knowledgeable."
              </p>
            </CardContent>
          </Card>

          <Card class="p-6">
            <CardContent>
              <div class="flex items-center gap-4 mb-4">
                <Avatar>
                  <AvatarImage src="/avatars/2.png" alt="Michael" />
                  <AvatarFallback>MC</AvatarFallback>
                </Avatar>
                <div>
                  <p class="font-semibold">Michael Chen</p>
                  <p class="text-sm text-muted-foreground">ML Engineer</p>
                </div>
              </div>
              <p class="text-muted-foreground">
                "The projects and discussions here have helped me grow both professionally and personally. Highly recommended!"
              </p>
            </CardContent>
          </Card>

          <Card class="p-6">
            <CardContent>
              <div class="flex items-center gap-4 mb-4">
                <Avatar>
                  <AvatarImage src="/avatars/3.png" alt="Emma" />
                  <AvatarFallback>EW</AvatarFallback>
                </Avatar>
                <div>
                  <p class="font-semibold">Emma Wilson</p>
                  <p class="text-sm text-muted-foreground">Data Scientist</p>
                </div>
              </div>
              <p class="text-muted-foreground">
                "The resources and networking opportunities at Inference.Club are unmatched. It's a must-join for anyone in AI."
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>

    <!-- CTA Section -->
    <section class="py-20 px-4 sm:px-6 lg:px-8">
      <div class="max-w-7xl mx-auto text-center">
        <h2 class="text-3xl font-bold mb-6">Ready to Join?</h2>
        <p class="text-xl text-muted-foreground mb-8">
          Become part of our growing community today and start your AI journey.
        </p>
        <Button size="lg" class="w-full sm:w-auto">
          Get Started Now
          <ArrowRight class="ml-2 h-4 w-4" />
        </Button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { ArrowRight } from 'lucide-vue-next'
</script>
