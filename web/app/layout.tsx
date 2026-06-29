import React from 'react';
import { Inter, JetBrains_Mono } from 'next/font/google';
import '@/styles/globals.css';
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
