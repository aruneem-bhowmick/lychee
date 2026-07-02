import React from 'react';
import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import '@/styles/globals.css';
import '@/styles/animations.css';
import NavBar from '@/components/NavBar';
import Footer from '@/components/Footer';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  weight: ['400', '500', '600', '700', '800']
});

const mono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
  weight: ['400']
});

const SITE_URL = 'https://lychee.vercel.app';
const VALUE_PROPOSITION =
  'Self-hosted, Claude-powered PR reviews that run concurrently, report cost to the cent, and never post twice.';

/**
 * Base, site-wide metadata inherited by every route. `metadataBase`
 * resolves the relative Open Graph image and canonical URLs declared by
 * individual pages; the title template appends `· Lychee Docs` to any page
 * that sets only a plain string `title` (the landing page opts out with an
 * absolute title). `/og-image.png` is a placeholder asset — swapping in
 * final artwork at the same path requires no code changes.
 */
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: 'Lychee — Peel back your pull requests',
    template: '%s · Lychee Docs',
  },
  description: VALUE_PROPOSITION,
  openGraph: {
    title: 'Lychee — Peel back your pull requests',
    description: VALUE_PROPOSITION,
    images: ['/og-image.png'],
    url: '/',
    siteName: 'Lychee',
    type: 'website',
  },
};

/**
 * Root layout component for the application.
 * Provides the base HTML shell with navigation, footer, and fonts.
 *
 * @param props - Layout properties.
 * @param props.children - The child components to render within the layout body.
 * @returns The root HTML element containing the rendered children.
 */
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body>
        <NavBar />
        <main id="main">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
