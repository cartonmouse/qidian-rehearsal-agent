const ICP_RECORD = "京ICP备2026057480号-2";

export default function ComplianceFooter() {
  return (
    <footer className="shrink-0 border-t border-border/60 px-4 py-4 text-center text-xs text-dim">
      <a
        href="https://beian.miit.gov.cn/"
        target="_blank"
        rel="noreferrer"
        className="transition-colors hover:text-text"
      >
        {ICP_RECORD}
      </a>
    </footer>
  );
}
