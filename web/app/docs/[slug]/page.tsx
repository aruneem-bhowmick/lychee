import type { Metadata } from 'next';
import { compileMDX } from 'next-mdx-remote/rsc';
import { getAllDocSlugs, getDocBySlug } from '@/lib/docs';
import { getRehypePlugins } from '@/lib/rehype-plugins';
import { remarkGfmTables } from '@/lib/remark-gfm-tables';
import DocsSidebar from '@/components/DocsSidebar';
import styles from '../docs.module.css';

export const dynamic = 'force-static';

/**
 * Returns the static params for every documentation slug so each doc page
 * can be fully prerendered at build time.
 *
 * @returns One params object per known doc slug.
 */
export function generateStaticParams(): Array<{ slug: string }> {
  return getAllDocSlugs().map((slug) => ({ slug }));
}

export interface DocPageRouteProps {
  params: Promise<{ slug: string }>;
}

/**
 * Builds per-doc metadata from the resolved doc's `title`/`description`.
 * The plain-string `title` picks up the root layout's `%s · Lychee Docs`
 * template for the `<title>` tag; `openGraph.title` restates that same
 * combined string explicitly, since Open Graph fields are not passed
 * through the title template.
 *
 * @param props - Route props containing the requested slug.
 * @returns The resolved metadata for the doc page.
 */
export async function generateMetadata({ params }: DocPageRouteProps): Promise<Metadata> {
  const { slug } = await params;
  const doc = getDocBySlug(slug);

  return {
    title: doc.title,
    description: doc.description,
    openGraph: {
      title: `${doc.title} · Lychee Docs`,
      description: doc.description,
      images: ['/og-image.png'],
      url: `/docs/${slug}`,
    },
    alternates: {
      canonical: `https://lychee.vercel.app/docs/${slug}`,
    },
  };
}

/**
 * Renders a single documentation page: the grouped sidebar alongside the
 * markdown body, compiled to MDX with GFM tables, syntax-highlighted code
 * blocks, heading anchors, and rewritten internal doc links.
 *
 * @param props - Route props containing the requested slug.
 * @returns The rendered doc page.
 */
export default async function DocPageRoute({ params }: DocPageRouteProps): Promise<JSX.Element> {
  const { slug } = await params;
  const doc = getDocBySlug(slug);

  const { content } = await compileMDX({
    source: doc.content,
    options: {
      mdxOptions: {
        remarkPlugins: [remarkGfmTables],
        rehypePlugins: getRehypePlugins(),
      },
    },
  });

  return (
    <div className={styles.layout}>
      <DocsSidebar activeSlug={doc.slug} />
      <article className={styles.prose}>{content}</article>
    </div>
  );
}
