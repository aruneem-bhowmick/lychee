import React from 'react';
import type { Metadata } from 'next';
import Hero from '@/components/Hero';
import FeatureHighlights from '@/components/FeatureHighlights';
import HowItWorks from '@/components/HowItWorks';
import SetupTabs from '@/components/SetupTabs';
import OutputShowcase from '@/components/OutputShowcase';
import CommandsTable from '@/components/CommandsTable';
import ConfigSampler from '@/components/ConfigSampler';
import ContributeSection from '@/components/ContributeSection';

export const dynamic = 'force-static';

const VALUE_PROPOSITION =
  'Self-hosted, Claude-powered PR reviews that run concurrently, report cost to the cent, and never post twice.';

/**
 * Landing page metadata. The title is set as `absolute` so the root
 * layout's `%s · Lychee Docs` template does not apply to it — the home
 * page keeps the bare tagline as its `<title>`.
 */
export const metadata: Metadata = {
  title: { absolute: 'Lychee — Peel back your pull requests' },
  description: VALUE_PROPOSITION,
  openGraph: {
    title: 'Lychee — Peel back your pull requests',
    description: VALUE_PROPOSITION,
    images: ['/og-image.png'],
  },
  alternates: {
    canonical: 'https://lychee.vercel.app/',
  },
};

/**
 * The main landing page composed of all its primary sections.
 *
 * @returns The fully assembled landing page.
 */
export default function Home(): JSX.Element {
  return (
    <>
      <Hero />
      <FeatureHighlights />
      <HowItWorks />
      <SetupTabs />
      <OutputShowcase />
      <CommandsTable />
      <ConfigSampler />
      <ContributeSection />
    </>
  );
}
