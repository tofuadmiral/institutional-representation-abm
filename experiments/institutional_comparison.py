#!/usr/bin/env python3
"""
Phase 1.3: Institutional Comparison Framework

This script provides a unified framework for comparing parliamentary and republican systems
on key representational metrics across controlled scenarios.

Key Comparisons:
- Legislative efficiency (passage rates)
- Representational quality (legislator-constituency alignment) 
- System stability (government/gridlock events)
- Committee performance (gatekeeping vs facilitation)
- Party discipline effects
- Institutional responsiveness to different bill types
"""

import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from typing import Dict, List, Any, Tuple
import json
from dataclasses import dataclass

from institutions.parliamentary import ParliamentaryModel
from institutions.republican import RepublicanModel
from bills.bill import Bill
from config import ParliamentaryConfig, RepublicanConfig


@dataclass
class ComparisonScenario:
    """Defines a scenario for institutional comparison."""
    name: str
    description: str
    num_legislators: int
    num_constituencies: int
    num_parties: int
    num_bills: int
    bill_ideology_range: Tuple[float, float]  # (min, max) for both dimensions
    seed: int = 42


@dataclass
class InstitutionConfig:
    """Configuration for an institutional system."""
    name: str
    model_class: Any
    config: Any  # ParliamentaryConfig or RepublicanConfig


class InstitutionalComparator:
    """Framework for systematic comparison of institutional systems."""
    
    def __init__(self):
        self.results: Dict[str, List[Dict]] = {}
        
    def define_scenarios(self) -> List[ComparisonScenario]:
        """Define standard comparison scenarios."""
        return [
            ComparisonScenario(
                name="baseline",
                description="Standard balanced scenario",
                num_legislators=20,
                num_constituencies=6,
                num_parties=3,
                num_bills=25,
                bill_ideology_range=(-1.0, 1.0),
                seed=42
            ),
            ComparisonScenario(
                name="fragmented",
                description="Many parties, coalition politics",
                num_legislators=24,
                num_constituencies=8,
                num_parties=5,
                num_bills=30,
                bill_ideology_range=(-1.0, 1.0),
                seed=42
            ),
            ComparisonScenario(
                name="polarized",
                description="Extreme bills, testing system limits",
                num_legislators=16,
                num_constituencies=4,
                num_parties=2,
                num_bills=20,
                bill_ideology_range=(-1.5, 1.5),  # More extreme bills
                seed=42
            ),
            ComparisonScenario(
                name="small_system",
                description="Minimal viable system",
                num_legislators=10,
                num_constituencies=3,
                num_parties=2,
                num_bills=15,
                bill_ideology_range=(-0.8, 0.8),
                seed=42
            )
        ]
    
    def define_institutions(self) -> List[InstitutionConfig]:
        """Define institutional configurations to compare."""
        return [
            InstitutionConfig(
                name="parliamentary",
                model_class=ParliamentaryModel,
                config=ParliamentaryConfig(),
            ),
            InstitutionConfig(
                name="republican",
                model_class=RepublicanModel,
                config=RepublicanConfig(),
            ),
        ]
    
    def generate_test_bills(self, scenario: ComparisonScenario, model) -> List[Bill]:
        """Generate standardized bills for testing."""
        bills = []
        
        for i in range(scenario.num_bills):
            ideology = (
                model.random.uniform(*scenario.bill_ideology_range),
                model.random.uniform(*scenario.bill_ideology_range)
            )
            
            bills.append(Bill(
                bill_id=i,
                ideology=ideology,
                salience=model.random.uniform(0.3, 1.0)
            ))
        
        return bills
    
    def run_comparison(self, scenario: ComparisonScenario, institution: InstitutionConfig) -> Dict[str, Any]:
        """Run a single institutional system through a scenario."""
        model = institution.model_class(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=institution.config,
            seed=scenario.seed,
        )
        
        # Generate test bills
        bills = self.generate_test_bills(scenario, model)
        
        # Track results
        bills_passed = 0
        bills_failed = 0
        committee_kills = 0
        
        # Process bills through system
        for bill in bills:
            if model.pass_legislation(bill):
                bills_passed += 1
            else:
                bills_failed += 1
        
        # Collect system-specific metrics
        if hasattr(model, 'get_government_stats'):
            # Parliamentary system
            gov_stats = model.get_government_stats()
            system_metrics = {
                'government_formed': gov_stats.get('government_formed', False),
                'coalition_size': gov_stats.get('coalition_size', 0),
                'confidence_votes_passed': gov_stats.get('confidence_votes_passed', 0),
                'confidence_votes_failed': gov_stats.get('confidence_votes_failed', 0),
                'bills_vetoed': 0,
                'gridlock_events': 0
            }
        else:
            # Republican system
            system_stats = model.get_system_stats()
            separation_stats = model.get_separation_of_powers_stats()
            system_metrics = {
                'government_formed': None,
                'coalition_size': 0,
                'confidence_votes_passed': 0,
                'confidence_votes_failed': 0,
                'bills_vetoed': system_stats.get('bills_vetoed', 0),
                'gridlock_events': system_stats.get('gridlock_events', 0),
                'divided_government': separation_stats.get('divided_government', False),
                'veto_rate': separation_stats.get('veto_rate', 0.0)
            }
        
        # Committee metrics
        committee_stats = model.get_committee_stats()
        
        # Calculate representational metrics
        representation_metrics = self._calculate_representation_metrics(model)
        
        return {
            'scenario': scenario.name,
            'institution': institution.name,
            'bills_processed': len(bills),
            'bills_passed': bills_passed,
            'bills_failed': bills_failed,
            'passage_rate': bills_passed / len(bills),
            'failure_rate': bills_failed / len(bills),
            
            # System-specific metrics
            **system_metrics,
            
            # Committee metrics
            'committee_kill_rate': committee_stats.get('avg_kill_rate', 0),
            'committee_amendment_rate': committee_stats.get('avg_amendment_rate', 0),
            'total_committee_bills': committee_stats.get('total_bills_considered', 0),
            
            # Representation metrics
            **representation_metrics,
            
            # System parameters
            'num_legislators': scenario.num_legislators,
            'num_parties': scenario.num_parties,
            'discipline_strength': institution.config.discipline_strength,
        }
    
    def _calculate_representation_metrics(self, model) -> Dict[str, float]:
        """Calculate representational quality metrics."""
        try:
            # Get legislators and constituencies
            legislators = []
            constituencies = {}
            
            for agent in model.schedule.agents:
                if hasattr(agent, 'ideology') and hasattr(agent, 'constituency_id'):
                    legislators.append(agent)
                elif hasattr(agent, 'ideology') and hasattr(agent, 'unique_id') and not hasattr(agent, 'party_id'):
                    # This is likely a constituency
                    constituencies[agent.unique_id] = agent
            
            if not legislators or not constituencies:
                return {
                    'avg_representation_distance': 0.0,
                    'representation_inequality': 0.0,
                    'perfect_representation_rate': 0.0
                }
            
            # Calculate distances
            distances = []
            for legislator in legislators:
                if legislator.constituency_id in constituencies:
                    constituency = constituencies[legislator.constituency_id]
                    dist = ((legislator.ideology[0] - constituency.ideology[0])**2 + 
                           (legislator.ideology[1] - constituency.ideology[1])**2)**0.5
                    distances.append(dist)
            
            if not distances:
                return {
                    'avg_representation_distance': 0.0,
                    'representation_inequality': 0.0,
                    'perfect_representation_rate': 0.0
                }
            
            # Calculate metrics
            avg_distance = sum(distances) / len(distances)
            
            # Inequality as variance
            mean_dist = avg_distance
            variance = sum((d - mean_dist)**2 for d in distances) / len(distances) if len(distances) > 1 else 0
            
            # Perfect representation rate (distance < 0.2)
            perfect_count = sum(1 for d in distances if d < 0.2)
            perfect_rate = perfect_count / len(distances)
            
            return {
                'avg_representation_distance': avg_distance,
                'representation_inequality': variance,
                'perfect_representation_rate': perfect_rate
            }
            
        except Exception as e:
            # Fallback if representation calculation fails
            return {
                'avg_representation_distance': 0.0,
                'representation_inequality': 0.0,
                'perfect_representation_rate': 0.0
            }
    
    def run_full_comparison(self) -> pd.DataFrame:
        """Run all scenarios across all institutions."""
        scenarios = self.define_scenarios()
        institutions = self.define_institutions()
        
        all_results = []
        
        print("Running institutional comparison across scenarios...")
        print("=" * 60)
        
        for scenario in scenarios:
            print(f"\nScenario: {scenario.name} - {scenario.description}")
            print(f"  Legislators: {scenario.num_legislators}, Parties: {scenario.num_parties}, Bills: {scenario.num_bills}")
            
            for institution in institutions:
                print(f"  Testing {institution.name}...", end=" ")
                
                try:
                    result = self.run_comparison(scenario, institution)
                    all_results.append(result)
                    print(f"✓ {result['bills_passed']}/{result['bills_processed']} passed")
                    
                except Exception as e:
                    print(f"✗ Error: {e}")
                    # Add error result
                    all_results.append({
                        'scenario': scenario.name,
                        'institution': institution.name,
                        'error': str(e),
                        'bills_passed': 0,
                        'bills_processed': 0,
                        'passage_rate': 0.0
                    })
        
        return pd.DataFrame(all_results)
    
    def analyze_results(self, results_df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze comparison results."""
        analysis = {}
        
        # Overall system comparison
        system_summary = results_df.groupby('institution').agg({
            'passage_rate': ['mean', 'std'],
            'committee_kill_rate': ['mean', 'std'],  
            'avg_representation_distance': ['mean', 'std']
        }).round(3)
        
        analysis['system_summary'] = system_summary
        
        # Scenario-specific analysis
        scenario_summary = results_df.groupby(['scenario', 'institution']).agg({
            'passage_rate': 'mean',
            'bills_vetoed': 'mean',
            'gridlock_events': 'mean',
            'committee_kill_rate': 'mean'
        }).round(3)
        
        analysis['scenario_breakdown'] = scenario_summary
        
        # Key findings
        parl_avg_passage = results_df[results_df['institution'] == 'parliamentary']['passage_rate'].mean()
        rep_avg_passage = results_df[results_df['institution'] == 'republican']['passage_rate'].mean()
        
        analysis['key_findings'] = {
            'parliamentary_avg_passage_rate': round(float(parl_avg_passage), 3),
            'republican_avg_passage_rate': round(float(rep_avg_passage), 3),
            'efficiency_difference': round(float(parl_avg_passage - rep_avg_passage), 3),
            'parliamentary_more_efficient': bool(parl_avg_passage > rep_avg_passage)
        }
        
        return analysis
    
    def print_analysis(self, results_df: pd.DataFrame, analysis: Dict[str, Any]):
        """Print formatted analysis results."""
        print("\n" + "=" * 60)
        print("INSTITUTIONAL COMPARISON ANALYSIS")
        print("=" * 60)
        
        # Key findings
        findings = analysis['key_findings']
        print(f"\n🏛️ KEY FINDINGS:")
        print(f"  Parliamentary passage rate: {findings['parliamentary_avg_passage_rate']:.1%}")
        print(f"  Republican passage rate: {findings['republican_avg_passage_rate']:.1%}")
        print(f"  Efficiency difference: {findings['efficiency_difference']:+.1%}")
        
        if findings['parliamentary_more_efficient']:
            print(f"  → Parliamentary systems are more efficient at passing legislation")
        else:
            print(f"  → Republican systems are more efficient at passing legislation")
        
        # System comparison table
        print(f"\n📊 SYSTEM PERFORMANCE SUMMARY:")
        parl_data = results_df[results_df['institution'] == 'parliamentary']
        rep_data = results_df[results_df['institution'] == 'republican']
        
        print(f"                           Parliamentary    Republican")
        print(f"  Passage Rate:           {parl_data['passage_rate'].mean():.1%}            {rep_data['passage_rate'].mean():.1%}")
        print(f"  Committee Kill Rate:    {parl_data['committee_kill_rate'].mean():.1%}            {rep_data['committee_kill_rate'].mean():.1%}")
        print(f"  Avg Representation:     {parl_data['avg_representation_distance'].mean():.2f}             {rep_data['avg_representation_distance'].mean():.2f}")
        
        # Scenario breakdown
        print(f"\n📋 SCENARIO BREAKDOWN:")
        for scenario in results_df['scenario'].unique():
            scenario_data = results_df[results_df['scenario'] == scenario]
            parl_passage = scenario_data[scenario_data['institution'] == 'parliamentary']['passage_rate'].iloc[0]
            rep_passage = scenario_data[scenario_data['institution'] == 'republican']['passage_rate'].iloc[0]
            
            print(f"  {scenario.capitalize():12} - Parl: {parl_passage:.1%}, Rep: {rep_passage:.1%}, Diff: {parl_passage-rep_passage:+.1%}")
        
        # System-specific metrics
        print(f"\n⚖️ SYSTEM-SPECIFIC FEATURES:")
        parl_confidence = parl_data['confidence_votes_passed'].sum()
        rep_vetoes = rep_data['bills_vetoed'].sum()
        rep_gridlock = rep_data['gridlock_events'].sum()
        
        print(f"  Parliamentary confidence votes: {parl_confidence}")
        print(f"  Republican vetoes: {rep_vetoes}")
        print(f"  Republican gridlock events: {rep_gridlock}")


def main():
    """Run the full institutional comparison."""
    comparator = InstitutionalComparator()
    
    # Run comparison
    results_df = comparator.run_full_comparison()
    
    # Analyze results
    analysis = comparator.analyze_results(results_df)
    
    # Print analysis
    comparator.print_analysis(results_df, analysis)
    
    # Save results
    output_file = "institutional_comparison_results.csv"
    results_df.to_csv(output_file, index=False)
    print(f"\n💾 Results saved to: {output_file}")
    
    # Save analysis JSON (key findings only to avoid serialization issues)
    analysis_file = "institutional_analysis.json" 
    with open(analysis_file, 'w') as f:
        json.dump(analysis['key_findings'], f, indent=2)
    print(f"💾 Analysis saved to: {analysis_file}")


if __name__ == "__main__":
    main()