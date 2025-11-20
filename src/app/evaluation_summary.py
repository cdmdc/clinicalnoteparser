"""Aggregate evaluation summary across multiple documents with visualizations."""

import json
import logging
import statistics
from pathlib import Path
from typing import Dict, List, Optional

try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None

logger = logging.getLogger(__name__)


def load_evaluation(evaluation_path: Path) -> Optional[Dict]:
    """Load evaluation JSON file.
    
    Args:
        evaluation_path: Path to evaluation.json file
        
    Returns:
        Dict with evaluation data, or None if file doesn't exist or is invalid
    """
    if not evaluation_path.exists():
        logger.warning(f"Evaluation file not found: {evaluation_path}")
        return None
    
    try:
        with open(evaluation_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load evaluation from {evaluation_path}: {e}")
        return None


def compute_statistics(values: List[float]) -> Dict:
    """Compute statistical summary for a list of values.
    
    Args:
        values: List of numeric values
        
    Returns:
        Dict with mean, median, min, max, std_dev, q25, q75
    """
    if not values:
        return {
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
            "std_dev": None,
            "q25": None,
            "q75": None,
            "count": 0,
        }
    
    sorted_values = sorted(values)
    return {
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "std_dev": round(statistics.stdev(values) if len(values) > 1 else 0.0, 4),
        "q25": round(sorted_values[len(sorted_values) // 4], 4) if len(sorted_values) > 0 else None,
        "q75": round(sorted_values[3 * len(sorted_values) // 4], 4) if len(sorted_values) > 0 else None,
        "count": len(values),
    }


def generate_evaluation_summary(
    document_ids: List[str],
    results_dir: Path = Path("results"),
    output_dir: Optional[Path] = None,
) -> Dict:
    """Generate aggregate evaluation summary across multiple documents.
    
    Args:
        document_ids: List of document IDs (e.g., ["0", "1", "2", ..., "10"])
        results_dir: Base results directory (default: "results")
        output_dir: Output directory for summary (default: results/eval_summary)
        
    Returns:
        Dict with aggregate statistics
    """
    if output_dir is None:
        output_dir = results_dir / "eval_summary"
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    
    # Load all evaluations
    evaluations = []
    valid_docs = []
    
    for doc_id in document_ids:
        eval_path = results_dir / doc_id / "evaluation.json"
        eval_data = load_evaluation(eval_path)
        if eval_data:
            evaluations.append(eval_data)
            valid_docs.append(doc_id)
        else:
            logger.warning(f"Skipping document {doc_id} (evaluation.json not found or invalid)")
    
    if not evaluations:
        logger.error("No valid evaluations found!")
        return {}
    
    logger.info(f"Loaded {len(evaluations)} evaluation(s) from {len(valid_docs)} document(s)")
    
    # Extract metrics
    summary_coverage = []
    plan_coverage = []
    overall_coverage = []
    validity_percentage = []
    hallucination_rate = []
    span_consistency = []
    avg_jaccard = []
    confidence_scores = []
    semantic_similarity = []
    section_mismatches_total = []
    span_out_of_bounds_total = []
    
    # Per-document data for plots
    doc_metrics = []
    
    for i, eval_data in enumerate(evaluations):
        doc_id = valid_docs[i]
        
        # Citation coverage
        cov = eval_data.get("citation_coverage", {})
        summary_coverage.append(cov.get("summary_coverage_percentage", 0.0))
        plan_coverage.append(cov.get("plan_coverage_percentage", 0.0))
        overall_coverage.append(cov.get("overall_coverage_percentage", 0.0))
        
        # Citation validity
        validity = eval_data.get("citation_validity", {})
        validity_percentage.append(validity.get("validity_percentage", 0.0))
        
        # Hallucination rate
        orphans = eval_data.get("orphan_claims", {})
        hallucination_rate.append(orphans.get("hallucination_rate_percentage", 0.0))
        
        # Span consistency
        span_cons = eval_data.get("span_consistency", {})
        span_consistency.append(span_cons.get("consistency_percentage", 0.0))
        
        # Citation overlap
        jaccard = eval_data.get("citation_overlap_jaccard", {})
        avg_jaccard.append(jaccard.get("average_jaccard_similarity", 0.0))
        
        # Confidence scores
        conf_dist = eval_data.get("summary_statistics", {}).get("confidence_score_distribution", {})
        if conf_dist.get("mean") is not None:
            confidence_scores.append(conf_dist["mean"])
        
        # Semantic accuracy
        sem_acc = eval_data.get("semantic_accuracy")
        if sem_acc and sem_acc.get("average_similarity") is not None:
            semantic_similarity.append(sem_acc["average_similarity"])
        
        # Section mismatches
        section_mismatches = eval_data.get("section_name_mismatches", {})
        section_mismatches_total.append(section_mismatches.get("total", 0))
        
        # Span out of bounds
        span_bounds = eval_data.get("span_out_of_chunk_bounds", {})
        span_out_of_bounds_total.append(span_bounds.get("total", 0))
        
        # Store per-document metrics
        doc_metrics.append({
            "doc_id": doc_id,
            "summary_coverage": cov.get("summary_coverage_percentage", 0.0),
            "plan_coverage": cov.get("plan_coverage_percentage", 0.0),
            "validity": validity.get("validity_percentage", 0.0),
            "hallucination_rate": orphans.get("hallucination_rate_percentage", 0.0),
            "semantic_similarity": sem_acc.get("average_similarity") if sem_acc else None,
            "confidence": conf_dist.get("mean") if conf_dist.get("mean") is not None else None,
        })
    
    # Compute aggregate statistics
    summary = {
        "total_documents": len(evaluations),
        "valid_documents": valid_docs,
        "citation_coverage": {
            "summary": compute_statistics(summary_coverage),
            "plan": compute_statistics(plan_coverage),
            "overall": compute_statistics(overall_coverage),
        },
        "citation_validity": compute_statistics(validity_percentage),
        "hallucination_rate": compute_statistics(hallucination_rate),
        "span_consistency": compute_statistics(span_consistency),
        "citation_overlap_jaccard": compute_statistics(avg_jaccard),
        "confidence_scores": compute_statistics(confidence_scores),
        "semantic_accuracy": compute_statistics(semantic_similarity) if semantic_similarity else None,
        "section_name_mismatches": {
            "total": compute_statistics(section_mismatches_total),
        },
        "span_out_of_chunk_bounds": {
            "total": compute_statistics(span_out_of_bounds_total),
        },
        "per_document": doc_metrics,
    }
    
    # Generate plots if matplotlib is available
    if MATPLOTLIB_AVAILABLE:
        generate_plots(summary, plots_dir, valid_docs)
    else:
        logger.warning("matplotlib not available, skipping plot generation")
    
    # Save summary JSON
    summary_path = output_dir / "evaluation_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved evaluation summary to {summary_path}")
    
    # Save human-readable summary
    text_summary_path = output_dir / "evaluation_summary.txt"
    save_text_summary(summary, text_summary_path)
    logger.info(f"Saved text summary to {text_summary_path}")
    
    return summary


def generate_plots(summary: Dict, plots_dir: Path, doc_ids: List[str]) -> None:
    """Generate visualization plots for evaluation metrics.
    
    Args:
        summary: Aggregate summary statistics
        plots_dir: Directory to save plots
        doc_ids: List of document IDs for labeling
    """
    if not MATPLOTLIB_AVAILABLE:
        return
    
    # Set style
    plt.style.use('default')
    fig_size = (10, 6)
    
    # 1. Citation Coverage Bar Chart
    fig, ax = plt.subplots(figsize=fig_size)
    coverage_data = summary["citation_coverage"]
    metrics = ["Summary", "Plan", "Overall"]
    means = [
        coverage_data["summary"]["mean"] or 0.0,
        coverage_data["plan"]["mean"] or 0.0,
        coverage_data["overall"]["mean"] or 0.0,
    ]
    stds = [
        coverage_data["summary"]["std_dev"] or 0.0,
        coverage_data["plan"]["std_dev"] or 0.0,
        coverage_data["overall"]["std_dev"] or 0.0,
    ]
    
    bars = ax.bar(metrics, means, yerr=stds, capsize=5, alpha=0.7, color=['#1f77b4', '#ff7f0e', '#2ca02c'])
    ax.set_ylabel('Coverage Percentage (%)')
    ax.set_title('Citation Coverage Across Documents')
    ax.set_ylim(0, 105)
    ax.grid(axis='y', alpha=0.3)
    
    # Add value labels on bars
    for bar, mean in zip(bars, means):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{mean:.1f}%', ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig(plots_dir / "citation_coverage.png", dpi=150, bbox_inches='tight')
    plt.close()
    
    # 2. Citation Validity and Hallucination Rate
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    # Validity
    validity_stats = summary["citation_validity"]
    ax1.barh(['Validity'], [validity_stats["mean"] or 0.0], 
             xerr=[validity_stats["std_dev"] or 0.0], capsize=5, alpha=0.7, color='#2ca02c')
    ax1.set_xlabel('Percentage (%)')
    ax1.set_title('Citation Validity')
    ax1.set_xlim(0, 105)
    ax1.text(validity_stats["mean"] or 0.0, 0, f'{validity_stats["mean"]:.1f}%', 
             ha='center', va='center', fontweight='bold')
    ax1.grid(axis='x', alpha=0.3)
    
    # Hallucination Rate
    halluc_stats = summary["hallucination_rate"]
    ax2.barh(['Hallucination\nRate'], [halluc_stats["mean"] or 0.0],
             xerr=[halluc_stats["std_dev"] or 0.0], capsize=5, alpha=0.7, color='#d62728')
    ax2.set_xlabel('Percentage (%)')
    ax2.set_title('Hallucination Rate (Lower is Better)')
    ax2.set_xlim(0, max(10, (halluc_stats["mean"] or 0.0) + (halluc_stats["std_dev"] or 0.0) + 2))
    ax2.text(halluc_stats["mean"] or 0.0, 0, f'{halluc_stats["mean"]:.2f}%',
             ha='center', va='center', fontweight='bold')
    ax2.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(plots_dir / "validity_hallucination.png", dpi=150, bbox_inches='tight')
    plt.close()
    
    # 3. Semantic Accuracy (if available)
    if summary.get("semantic_accuracy") and summary["semantic_accuracy"]["count"] > 0:
        fig, ax = plt.subplots(figsize=fig_size)
        sem_stats = summary["semantic_accuracy"]
        
        # Box plot data from per-document metrics
        sem_similarities = [m["semantic_similarity"] for m in summary["per_document"] 
                           if m.get("semantic_similarity") is not None]
        
        if sem_similarities:
            ax.boxplot(sem_similarities, vert=True, patch_artist=True,
                      boxprops=dict(facecolor='#9467bd', alpha=0.7))
            ax.set_ylabel('Similarity Score')
            ax.set_title('Semantic Accuracy (Similarity Scores)')
            ax.set_xticklabels(['Similarity'])
            ax.set_ylim(0, 1.1)
            ax.axhline(y=0.7, color='r', linestyle='--', alpha=0.5, label='Threshold (0.7)')
            ax.legend()
            ax.grid(axis='y', alpha=0.3)
            
            # Add mean line
            mean_val = sem_stats["mean"] or 0.0
            ax.axhline(y=mean_val, color='g', linestyle='-', alpha=0.5, label=f'Mean ({mean_val:.3f})')
            ax.legend()
        
        plt.tight_layout()
        plt.savefig(plots_dir / "semantic_accuracy.png", dpi=150, bbox_inches='tight')
        plt.close()
    
    # 4. Confidence Score Distribution
    if summary["confidence_scores"]["count"] > 0:
        fig, ax = plt.subplots(figsize=fig_size)
        conf_scores = [m.get("confidence") for m in summary["per_document"] 
                      if m.get("confidence") is not None]
        # Extract from per-document if available, otherwise use aggregate
        if not conf_scores:
            # Try to reconstruct from aggregate stats
            conf_stats = summary["confidence_scores"]
            if conf_stats["count"] > 0:
                # Create a simple bar showing mean
                ax.barh(['Confidence'], [conf_stats["mean"] or 0.0],
                       alpha=0.7, color='#8c564b')
                ax.set_xlabel('Score')
                ax.set_title('Average Confidence Score')
                ax.set_xlim(0, 1.1)
                ax.text(conf_stats["mean"] or 0.0, 0, f'{conf_stats["mean"]:.2f}',
                       ha='center', va='center', fontweight='bold')
                ax.grid(axis='x', alpha=0.3)
        else:
            ax.hist(conf_scores, bins=10, alpha=0.7, color='#8c564b', edgecolor='black')
            ax.set_xlabel('Confidence Score')
            ax.set_ylabel('Frequency')
            ax.set_title('Confidence Score Distribution')
            ax.set_xlim(0, 1.1)
            ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(plots_dir / "confidence_distribution.png", dpi=150, bbox_inches='tight')
        plt.close()
    
    # 5. Per-Document Metrics Overview
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Coverage by document
    ax = axes[0, 0]
    doc_ids_short = [d[:10] for d in doc_ids]  # Truncate long IDs
    ax.plot(doc_ids_short, [m["summary_coverage"] for m in summary["per_document"]], 
            marker='o', label='Summary', alpha=0.7)
    ax.plot(doc_ids_short, [m["plan_coverage"] for m in summary["per_document"]], 
            marker='s', label='Plan', alpha=0.7)
    ax.set_ylabel('Coverage (%)')
    ax.set_title('Citation Coverage by Document')
    ax.legend()
    ax.grid(alpha=0.3)
    ax.set_ylim(0, 105)
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # Validity by document
    ax = axes[0, 1]
    ax.plot(doc_ids_short, [m["validity"] for m in summary["per_document"]], 
            marker='o', color='green', alpha=0.7)
    ax.set_ylabel('Validity (%)')
    ax.set_title('Citation Validity by Document')
    ax.grid(alpha=0.3)
    ax.set_ylim(0, 105)
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # Hallucination rate by document
    ax = axes[1, 0]
    ax.plot(doc_ids_short, [m["hallucination_rate"] for m in summary["per_document"]], 
            marker='o', color='red', alpha=0.7)
    ax.set_ylabel('Hallucination Rate (%)')
    ax.set_title('Hallucination Rate by Document')
    ax.grid(alpha=0.3)
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # Semantic similarity by document (if available)
    ax = axes[1, 1]
    sem_sims = [m.get("semantic_similarity") for m in summary["per_document"] 
                if m.get("semantic_similarity") is not None]
    sem_doc_ids = [doc_ids_short[i] for i, m in enumerate(summary["per_document"]) 
                   if m.get("semantic_similarity") is not None]
    if sem_sims:
        ax.plot(sem_doc_ids, sem_sims, marker='o', color='purple', alpha=0.7)
        ax.axhline(y=0.7, color='r', linestyle='--', alpha=0.5, label='Threshold')
        ax.set_ylabel('Similarity Score')
        ax.set_title('Semantic Similarity by Document')
        ax.set_ylim(0, 1.1)
        ax.legend()
        ax.grid(alpha=0.3)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    else:
        ax.text(0.5, 0.5, 'No semantic accuracy data', 
               ha='center', va='center', transform=ax.transAxes)
        ax.set_title('Semantic Similarity by Document')
    
    plt.tight_layout()
    plt.savefig(plots_dir / "metrics_overview.png", dpi=150, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Generated {len(list(plots_dir.glob('*.png')))} plot(s) in {plots_dir}")


def save_text_summary(summary: Dict, output_path: Path) -> None:
    """Save human-readable text summary.
    
    Args:
        summary: Aggregate summary statistics
        output_path: Path to save text summary
    """
    lines = []
    lines.append("=" * 80)
    lines.append("EVALUATION SUMMARY")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Total Documents Evaluated: {summary['total_documents']}")
    lines.append(f"Valid Documents: {', '.join(summary['valid_documents'])}")
    lines.append("")
    
    # Citation Coverage
    lines.append("CITATION COVERAGE")
    lines.append("-" * 80)
    cov = summary["citation_coverage"]
    for metric_name, metric_key in [("Summary", "summary"), ("Plan", "plan"), ("Overall", "overall")]:
        stats = cov[metric_key]
        lines.append(f"{metric_name}:")
        lines.append(f"  Mean: {stats['mean']:.2f}%")
        lines.append(f"  Median: {stats['median']:.2f}%")
        lines.append(f"  Min: {stats['min']:.2f}%, Max: {stats['max']:.2f}%")
        lines.append(f"  Std Dev: {stats['std_dev']:.2f}%")
        lines.append("")
    
    # Citation Validity
    lines.append("CITATION VALIDITY")
    lines.append("-" * 80)
    validity = summary["citation_validity"]
    lines.append(f"Mean: {validity['mean']:.2f}%")
    lines.append(f"Median: {validity['median']:.2f}%")
    lines.append(f"Min: {validity['min']:.2f}%, Max: {validity['max']:.2f}%")
    lines.append(f"Std Dev: {validity['std_dev']:.2f}%")
    lines.append("")
    
    # Hallucination Rate
    lines.append("HALLUCINATION RATE")
    lines.append("-" * 80)
    halluc = summary["hallucination_rate"]
    lines.append(f"Mean: {halluc['mean']:.2f}%")
    lines.append(f"Median: {halluc['median']:.2f}%")
    lines.append(f"Min: {halluc['min']:.2f}%, Max: {halluc['max']:.2f}%")
    lines.append(f"Std Dev: {halluc['std_dev']:.2f}%")
    lines.append("")
    
    # Semantic Accuracy
    if summary.get("semantic_accuracy") and summary["semantic_accuracy"]["count"] > 0:
        lines.append("SEMANTIC ACCURACY")
        lines.append("-" * 80)
        sem = summary["semantic_accuracy"]
        lines.append(f"Mean Similarity: {sem['mean']:.4f}")
        lines.append(f"Median: {sem['median']:.4f}")
        lines.append(f"Min: {sem['min']:.4f}, Max: {sem['max']:.4f}")
        lines.append(f"Std Dev: {sem['std_dev']:.4f}")
        lines.append(f"Documents with data: {sem['count']}")
        lines.append("")
    
    # Span Consistency
    lines.append("SPAN CONSISTENCY")
    lines.append("-" * 80)
    span = summary["span_consistency"]
    lines.append(f"Mean: {span['mean']:.2f}%")
    lines.append(f"Median: {span['median']:.2f}%")
    lines.append("")
    
    # Citation Overlap
    lines.append("CITATION OVERLAP (JACCARD)")
    lines.append("-" * 80)
    jaccard = summary["citation_overlap_jaccard"]
    lines.append(f"Mean: {jaccard['mean']:.4f}")
    lines.append(f"Median: {jaccard['median']:.4f}")
    lines.append("")
    
    # Confidence Scores
    if summary["confidence_scores"]["count"] > 0:
        lines.append("CONFIDENCE SCORES")
        lines.append("-" * 80)
        conf = summary["confidence_scores"]
        lines.append(f"Mean: {conf['mean']:.2f}")
        lines.append(f"Median: {conf['median']:.2f}")
        lines.append(f"Min: {conf['min']:.2f}, Max: {conf['max']:.2f}")
        lines.append("")
    
    # Section Mismatches
    lines.append("SECTION NAME MISMATCHES")
    lines.append("-" * 80)
    section = summary["section_name_mismatches"]["total"]
    if section['mean'] is not None:
        lines.append(f"Mean: {section['mean']:.2f}")
        lines.append(f"Median: {section['median']:.2f}")
        lines.append(f"Min: {section['min']:.0f}, Max: {section['max']:.0f}")
    else:
        lines.append("No data available")
    lines.append("")
    
    # Span Out of Bounds
    lines.append("SPAN OUT OF CHUNK BOUNDS")
    lines.append("-" * 80)
    span_bounds = summary["span_out_of_chunk_bounds"]["total"]
    if span_bounds['mean'] is not None:
        lines.append(f"Mean: {span_bounds['mean']:.2f}")
        lines.append(f"Median: {span_bounds['median']:.2f}")
        lines.append(f"Min: {span_bounds['min']:.0f}, Max: {span_bounds['max']:.0f}")
    else:
        lines.append("No data available")
    lines.append("")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

