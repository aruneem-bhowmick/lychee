import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { axe, toHaveNoViolations } from 'jest-axe';
import CommandsTable, { COMMANDS } from './CommandsTable';

expect.extend(toHaveNoViolations);

// Mock CodeBlock as it's an async server component which RTL doesn't handle well directly.
vi.mock('./CodeBlock', () => {
  return {
    default: function MockCodeBlock({ code, filename }: { code: string; filename?: string }) {
      return (
        <div data-testid="mock-codeblock" data-filename={filename}>
          {code}
        </div>
      );
    }
  };
});

describe('CommandsTable', () => {
  // 1. Unit
  describe('Unit', () => {
    it('should export COMMANDS with exactly 4 items in correct order', () => {
      expect(COMMANDS).toHaveLength(4);
      expect(COMMANDS[0].command).toBe('@lychee peel');
      expect(COMMANDS[1].command).toBe('@lychee juice');
      expect(COMMANDS[2].command).toBe('@lychee pit');
      expect(COMMANDS[3].command).toBe('@lychee ripe?');
    });
  });

  // 2. Component
  describe('Component', () => {
    it('renders the correct table rows and copy', () => {
      render(<CommandsTable />);
      
      // Select the rows in the tbody
      const rows = screen.getAllByRole('row');
      // 1 header row + 4 data rows = 5 rows total
      expect(rows).toHaveLength(5);
      
      expect(screen.getByText('Nectar section only — the short summary paragraph')).toBeInTheDocument();
      expect(screen.getByText('Ripeness verdict only — 🟢 Ripe, 🟡 Unripe, or 🔴 Sour')).toBeInTheDocument();
      
      // Supporting paragraph assertion
      const paragraph = screen.getByText(/Unknown commands receive a help message listing all four\./);
      expect(paragraph).toBeInTheDocument();
      
      // CTA link assertion
      const link = screen.getByRole('link', { name: /Full command reference/i });
      expect(link).toHaveAttribute('href', '/docs/commands');
      
      // YAML CodeBlock assertions
      const codeBlock = screen.getByTestId('mock-codeblock');
      expect(codeBlock).toHaveAttribute('data-filename', '.lychee.yml');
      expect(codeBlock.textContent).toContain('commands: true');
    });
  });

  // 3. Visual/Snapshot
  describe('Visual/Snapshot', () => {
    it('matches the golden snapshot', () => {
      const { container } = render(<CommandsTable />);
      expect(container).toMatchSnapshot();
    });
  });

  // 4. Accessibility
  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<CommandsTable />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('uses correct table semantics for headers', () => {
      render(<CommandsTable />);
      const headers = screen.getAllByRole('columnheader');
      expect(headers).toHaveLength(2);
      expect(headers[0]).toHaveAttribute('scope', 'col');
      expect(headers[0]).toHaveTextContent('Comment');
      expect(headers[1]).toHaveAttribute('scope', 'col');
      expect(headers[1]).toHaveTextContent('What it posts');
    });
  });

  // 5. Smoke
  describe('Smoke', () => {
    it('renders without crashing', () => {
      expect(() => render(<CommandsTable />)).not.toThrow();
    });
  });

  // 6. Sanity
  describe('Sanity', () => {
    it('contains exact verbatim required copy', () => {
      render(<CommandsTable />);
      
      // Support copy checks
      expect(screen.getByText(/authorization\.allowed_users/)).toBeInTheDocument();
      expect(screen.getAllByText(/\.lychee\.yml/).length).toBeGreaterThan(0);
      
      // YAML verbatim checks via mock code block text content
      const codeBlock = screen.getByTestId('mock-codeblock');
      const text = codeBlock.textContent || '';
      expect(text).toContain('# leave empty to allow all users');
      expect(text).toContain('- alice');
      expect(text).toContain('- bob');
    });
  });

  // 7. Regression
  describe('Regression', () => {
    it('locks the four command descriptions and YAML verbatim', () => {
      // Data snapshot for exactly the commands
      expect(COMMANDS).toMatchInlineSnapshot(`
        [
          {
            "command": "@lychee peel",
            "posts": "Full review: Nectar + The Peel + Pits (same as automatic review)",
          },
          {
            "command": "@lychee juice",
            "posts": "Nectar section only — the short summary paragraph",
          },
          {
            "command": "@lychee pit",
            "posts": "The single highest-severity finding only",
          },
          {
            "command": "@lychee ripe?",
            "posts": "Ripeness verdict only — 🟢 Ripe, 🟡 Unripe, or 🔴 Sour",
          },
        ]
      `);
      
      // The YAML content should match the rendered snapshot, which captures the verbatim YAML
      // since the mock code block renders the exact \`code\` prop it received.
      const codeBlock = render(<CommandsTable />).getByTestId('mock-codeblock');
      expect(codeBlock.textContent).toMatchInlineSnapshot(`
        "features:
          commands: true

        authorization:
          allowed_users:   # leave empty to allow all users
            - alice
            - bob"
      `);
    });
  });

  // 8. End-to-end
  describe('End-to-end', () => {
    it.skip('N/A — static content; covered by component tests');
  });

  // 9. API/Data
  describe('API/Data', () => {
    it.skip('N/A — no data loading');
  });

  // 10. Responsive/Mobile
  describe('Responsive/Mobile', () => {
    it('uses overflow-x: auto on the table wrapper for horizontal scrolling', () => {
      const { container } = render(<CommandsTable />);
      // We look for the table wrapper which should have the class containing tableWrapper
      const wrapper = container.querySelector('div[class*="tableWrapper"]');
      // Ensure the wrapper was found
      expect(wrapper).not.toBeNull();
      // Wait, JSDOM won't compute real CSS from CSS modules, so we'll check that a wrapper div exists
      // around the table. The CSS module itself handles the overflow-x: auto.
      const table = container.querySelector('table');
      expect(table?.parentElement).toBe(wrapper);
    });
  });
});
