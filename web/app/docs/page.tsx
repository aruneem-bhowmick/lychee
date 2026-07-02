import type { Metadata } from 'next';
import { getDocBySlug } from '@/lib/docs';
import DocsSidebar from '@/components/DocsSidebar';
import { DOC_LABELS, DOCS_INDEX_GROUPS } from './docs-index-groups';
import docsStyles from './docs.module.css';
import styles from './page.module.css';

export const dynamic = 'force-static';

/**
 * Docs index metadata. `title` is a plain string so the root layout's
 * template renders it as `Documentation · Lychee Docs`.
 */
export const metadata: Metadata = {
  title: 'Documentation',
  description: 'Everything you need to evaluate, run, and contribute to Lychee.',
  alternates: {
    canonical: 'https://lychee.vercel.app/docs',
  },
  openGraph: {
    images: ['/og-image.png'],
  },
};

/**
 * Renders the documentation table of contents at `/docs`: the grouped
 * sidebar alongside a set of section cards, one per doc, each linking to
 * its route with a one-sentence description drawn from the doc itself.
 *
 * @returns The rendered docs index page.
 */
export default function DocsIndexPage(): JSX.Element {
  return (
    <div className={docsStyles.layout}>
      <DocsSidebar activeSlug="" />
      <div className={styles.content}>
        <h1>Documentation</h1>
        <p className={styles.intro}>
          Everything you need to evaluate, run, and contribute to Lychee.
        </p>
        {DOCS_INDEX_GROUPS.map((group) => (
          <section key={group.section} className={styles.group}>
            <h2>{group.section}</h2>
            <dl className={styles.entries}>
              {group.slugs.map((slug) => {
                const { description } = getDocBySlug(slug);
                return (
                  <div key={slug} className={styles.card}>
                    <dt className={styles.cardTitle}>
                      <a href={`/docs/${slug}`}>{DOC_LABELS[slug]}</a>
                    </dt>
                    <dd className={styles.cardDescription}>{description}</dd>
                  </div>
                );
              })}
            </dl>
          </section>
        ))}
      </div>
    </div>
  );
}
