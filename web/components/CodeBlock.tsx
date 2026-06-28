import { highlightCode } from '../lib/highlight';
import CopyButton from './CopyButton';
import styles from './CodeBlock.module.css';

export interface CodeBlockProps {
  /** The raw source text to display */
  code: string;
  /** Language identifier for shiki highlighting and label */
  lang?: string;
  /** Optional override for the corner tag */
  label?: string;
  /** Optional filename shown above the block */
  filename?: string;
}

/**
 * An async server component that renders a highlighted block of code.
 * Includes a language tag, optional filename, and a client-side copy button.
 *
 * @param props - Props containing the code, language, and optional metadata.
 * @returns The server component rendering a figure with code and metadata.
 */
export default async function CodeBlock({
  code,
  lang = 'text',
  label,
  filename,
}: CodeBlockProps): Promise<JSX.Element> {
  const displayLabel = label ?? lang;
  const html = await highlightCode({ code, lang });

  return (
    <figure className={styles.wrapper}>
      {filename && <figcaption className={styles.filename}>{filename}</figcaption>}
      <div className={styles.frame}>
        <span className={styles.langTag} aria-hidden="true">
          {displayLabel}
        </span>
        <div className={styles.copyButtonWrapper}>
          <CopyButton text={code} />
        </div>
        <div
          className={styles.code}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </div>
    </figure>
  );
}
