import os
from typing import List, Tuple, Optional, Callable

# Expected domains and minimum file counts for a non-trivial project
EXPECTED_DOMAINS = {
    "output": 1,
    "output/config": 2,
    "output/src/core": 1,
    "output/src/entities": 1,
    "output/src/world": 1,
    "output/src/physics": 1,
    "output/src/ai": 1,
    "output/src/missions": 1,
    "output/src/inventory": 1,
    "output/src/audio": 1,
    "output/src/ui": 1,
    "output/src/networking": 1,
    "output/src/utils": 1,
}


def _count_files_by_prefix(workspace_dir: str, prefix: str) -> int:
    """Count files in a subdirectory."""
    count = 0
    target_dir = os.path.join(workspace_dir, prefix)
    if os.path.isdir(target_dir):
        for f in os.listdir(target_dir):
            fp = os.path.join(target_dir, f)
            if os.path.isfile(fp) and not f.startswith("."):
                count += 1
    return count


def verify_execution(
    workspace_dir: str,
    plan: str,
    steps: List[str],
    get_generate_fn,
    stream_callback: Optional[Callable[[str], None]] = None,
    complexity: str = "complex",
) -> Tuple[str, str]:
    total_files = 0
    domain_results = []
    missing_domains = []

    if complexity == "simple":
        output_dir = os.path.join(workspace_dir, "output")
        if not os.path.isdir(output_dir):
            total_files = 0
            domain_results.append("  ❌ output: directory does not exist")
        else:
            for f in os.listdir(output_dir):
                fp = os.path.join(output_dir, f)
                if os.path.isfile(fp) and not f.startswith("."):
                    total_files += 1
            domain_results.append(f"  output: {total_files} file(s)")
        analysis_lines = [
            f"Total files in workspace: {total_files}",
            "Simple mode — only checking that files exist:",
        ] + domain_results
        if total_files >= 1:
            verdict = "SUCCESS"
            analysis_lines.append("Files were generated successfully.")
        else:
            verdict = "FAILED"
            analysis_lines.append("No files found in output directory.")
    else:
        for domain, min_count in EXPECTED_DOMAINS.items():
            count = _count_files_by_prefix(workspace_dir, domain)
            total_files += count
            if count >= min_count:
                domain_results.append(f"  ✅ {domain}: {count} file(s)")
            else:
                domain_results.append(f"  ❌ {domain}: {count} file(s) (expected {min_count})")
                missing_domains.append(domain)

        analysis_lines = [
            f"Total files in workspace: {total_files}",
            "Domain breakdown:",
        ] + domain_results

        if missing_domains:
            analysis_lines.append(f"\nMissing/underpopulated domains: {', '.join(missing_domains)}")
            verdict = "FAILED"
            analysis_lines.append("Some expected domains have insufficient files.")
        elif total_files >= 15:
            verdict = "SUCCESS"
            analysis_lines.append("All expected domains have sufficient files.")
        else:
            verdict = "FAILED"
            analysis_lines.append("Very few files generated.")

    analysis = "\n".join(analysis_lines)

    return verdict, analysis
