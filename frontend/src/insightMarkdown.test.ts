import { describe, expect, it } from "vitest";
import { insightFilename, insightMarkdown } from "./insightMarkdown";

describe("insight markdown export", () => {
  const at = new Date(2026, 9, 13, 9, 5);
  it("includes heading, provider, question, text and disclaimer", () => {
    const md = insightMarkdown({ portfolio: "Main", taskLabel: "Ask a question", question: " Why? ", provider: "OpenAI",
      model: "gpt-5-mini", text: "Facts\n- A\n", disclaimer: "Not financial advice.", generatedAt: at });
    expect(md.startsWith("# Ask a question: Main\n")).toBe(true);
    expect(md).toContain("- **AI provider:** OpenAI (gpt-5-mini)");
    expect(md).toContain("- **Question:** Why?");
    expect(md).toContain("Facts\n- A\n\n---");
    expect(md).toContain("> Not financial advice.");
  });
  it("omits an empty question", () => {
    const md = insightMarkdown({ portfolio: "P", taskLabel: "Risk", provider: "x", model: "y", text: "t", disclaimer: "d", generatedAt: at });
    expect(md).not.toContain("Question");
  });
  it("builds a safe timestamped filename", () => {
    expect(insightFilename("Demo Portfolio!", "portfolio_summary", at)).toBe("insight-demo-portfolio-portfolio-summary-20261013-0905.md");
  });
});
