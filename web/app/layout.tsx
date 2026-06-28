import React from 'react';

/**
 * Root layout component for the application.
 * Provides the base HTML shell.
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
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
