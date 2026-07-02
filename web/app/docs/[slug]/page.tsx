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

// Per-page <title>/<meta> generation is not implemented yet; this route
// currently relies on the root layout's defaults.

export interface DocPageRouteProps {
  params: { slug: string };
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
  const doc = getDocBySlug(params.slug);

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
