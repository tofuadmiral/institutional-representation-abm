#!/usr/bin/env bash
set -euo pipefail

paper_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stage_dir="$(mktemp -d)"
trap 'rm -rf "$stage_dir"' EXIT
bst_path="$(kpsewhich plainurl.bst)"

if [[ -z "$bst_path" ]]; then
  echo "plainurl.bst was not found in the TeX installation" >&2
  exit 1
fi

mkdir -p "$stage_dir/figures" "$stage_dir/tables"
cp "$paper_dir/main.tex" "$stage_dir/"
cp "$paper_dir/main.bbl" "$stage_dir/"
cp "$paper_dir/references.bib" "$stage_dir/"
cp "$bst_path" "$stage_dir/plainurl.bst"
cp "$paper_dir/figures/state_conditional_effects.pdf" "$stage_dir/figures/"
cp "$paper_dir/figures/prevalence_frontiers.pdf" "$stage_dir/figures/"
cp "$paper_dir/figures/natural_proposal_outcomes.pdf" "$stage_dir/figures/"
cp "$paper_dir/tables/state_effects.tex" "$stage_dir/tables/"
cp "$paper_dir/tables/natural_results.tex" "$stage_dir/tables/"

COPYFILE_DISABLE=1 tar -C "$stage_dir" -czf "$paper_dir/arxiv-submission.tar.gz" \
  main.tex main.bbl references.bib plainurl.bst figures tables
echo "Created $paper_dir/arxiv-submission.tar.gz"
