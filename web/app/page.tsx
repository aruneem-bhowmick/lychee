import React from 'react';
import Hero from '@/components/Hero';
import FeatureHighlights from '@/components/FeatureHighlights';
import HowItWorks from '@/components/HowItWorks';
import SetupTabs from '@/components/SetupTabs';
import OutputShowcase from '@/components/OutputShowcase';
import CommandsTable from '@/components/CommandsTable';
import ConfigSampler from '@/components/ConfigSampler';
import ContributeSection from '@/components/ContributeSection';

export const dynamic = 'force-static';

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
