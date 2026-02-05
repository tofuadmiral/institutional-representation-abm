#!/usr/bin/env python3
"""
Test Phase 1.2: Republican/Presidential System Implementation

This script tests the republican system features:
- Executive election and separation of powers
- Weak party discipline vs parliamentary
- Committee-based agenda setting
- Executive veto powers
- Gridlock scenarios
- Fixed terms (no confidence votes)
"""

import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from institutions.republican import RepublicanModel
from bills.bill import Bill


def test_executive_election():
    """Test executive election and separation of powers setup."""
    print("=== Testing Executive Election ===")
    
    model = RepublicanModel(
        num_legislators=20,
        num_constituencies=6,
        num_parties=3,
        discipline_strength=0.4,
        seed=42
    )
    
    system_stats = model.get_system_stats()
    separation_stats = model.get_separation_of_powers_stats()
    
    print(f"Executive party: {system_stats['executive_party']}")
    print(f"President ID: {system_stats['president_id']}")
    print(f"Legislative majority party: {separation_stats['legislative_majority_party']}")
    print(f"Divided government: {separation_stats['divided_government']}")
    print(f"Party seat distribution: {separation_stats['legislative_party_seats']}")
    print(f"Discipline strength: {system_stats['discipline_strength']}")


def test_weak_party_discipline():
    """Test that republican system has weaker party discipline than parliamentary."""
    print("\n=== Testing Weak Party Discipline ===")
    
    # Test with different discipline strengths
    for strength in [0.2, 0.4, 0.6]:
        print(f"\nTesting discipline strength: {strength}")
        
        model = RepublicanModel(
            num_legislators=15,
            num_constituencies=5,
            num_parties=2,
            discipline_strength=strength,
            seed=42
        )
        
        # Create a bill and see voting patterns
        test_bill = Bill(bill_id=1, ideology=(0.5, 0.3), salience=0.8)
        
        # Count individual vs party votes
        individual_votes = 0
        party_line_votes = 0
        
        for agent in model.schedule.agents:
            if hasattr(agent, 'party_id') and agent.party_id is not None:
                # Compare individual preference vs party line
                individual_vote = agent.decide_vote(test_bill)
                disciplined_vote = model._get_weak_disciplined_vote(agent, test_bill)
                
                if individual_vote == disciplined_vote:
                    individual_votes += 1
                else:
                    party_line_votes += 1
        
        total_votes = individual_votes + party_line_votes
        if total_votes > 0:
            print(f"  Individual voting: {individual_votes}/{total_votes} ({individual_votes/total_votes:.1%})")
            print(f"  Party line voting: {party_line_votes}/{total_votes} ({party_line_votes/total_votes:.1%})")


def test_executive_veto():
    """Test executive veto powers and override attempts."""
    print("\n=== Testing Executive Veto ===")
    
    model = RepublicanModel(
        num_legislators=20,
        num_constituencies=6,
        num_parties=2,
        executive_opposition_rate=0.5,  # High veto rate for testing
        seed=42
    )
    
    # Test bills with different ideological distances from executive
    if model.president:
        exec_ideology = model.executive_ideology
        print(f"Executive ideology: {exec_ideology}")
        
        test_bills = [
            Bill(bill_id=1, ideology=exec_ideology, salience=0.8),  # Close to executive
            Bill(bill_id=2, ideology=(exec_ideology[0] + 0.5, exec_ideology[1]), salience=0.8),  # Moderate distance
            Bill(bill_id=3, ideology=(exec_ideology[0] - 1.0, exec_ideology[1] + 1.0), salience=0.8),  # Far from executive
        ]
        
        for bill in test_bills:
            veto = model._executive_veto_check(bill)
            distance = sum((a - b) ** 2 for a, b in zip(exec_ideology, bill.ideology)) ** 0.5
            print(f"Bill {bill.bill_id} (distance: {distance:.2f}): {'VETOED' if veto else 'SIGNED'}")


def test_legislative_process():
    """Test full republican legislative process."""
    print("\n=== Testing Legislative Process ===")
    
    model = RepublicanModel(
        num_legislators=15,
        num_constituencies=5,
        num_parties=3,
        discipline_strength=0.4,
        committee_gatekeeping_power=0.5,
        executive_opposition_rate=0.3,
        seed=42
    )
    
    # Pass multiple bills through the system
    test_bills = [
        Bill(bill_id=i, ideology=(
            model.random.uniform(-1, 1), 
            model.random.uniform(-1, 1)
        ), salience=0.5) 
        for i in range(15)
    ]
    
    print(f"Processing {len(test_bills)} bills through republican system...")
    
    passed_count = 0
    for bill in test_bills:
        if model.pass_legislation(bill):
            passed_count += 1
    
    system_stats = model.get_system_stats()
    separation_stats = model.get_separation_of_powers_stats()
    committee_stats = model.get_committee_stats()
    
    print(f"\nResults: {passed_count}/{len(test_bills)} bills became law")
    print(f"Bills vetoed: {system_stats['bills_vetoed']}")
    print(f"Gridlock events: {system_stats['gridlock_events']}")
    print(f"Veto rate: {separation_stats['veto_rate']:.1%}")
    print(f"Gridlock rate: {separation_stats['gridlock_rate']:.1%}")
    
    print(f"\nCommittee Performance:")
    print(f"  Bills killed by committees: {committee_stats['total_bills_killed']}")
    print(f"  Committee kill rate: {committee_stats['avg_kill_rate']:.1%}")
    print(f"  Amendment rate: {committee_stats['avg_amendment_rate']:.1%}")


def test_gridlock_scenarios():
    """Test various gridlock scenarios."""
    print("\n=== Testing Gridlock Scenarios ===")
    
    # Test with high opposition to create gridlock
    model = RepublicanModel(
        num_legislators=12,
        num_constituencies=4,
        num_parties=2,
        discipline_strength=0.6,  # Stronger discipline for clearer party divisions
        executive_opposition_rate=0.8,  # High executive opposition
        committee_gatekeeping_power=0.6,  # Strong committee gatekeeping
        seed=42
    )
    
    separation_stats = model.get_separation_of_powers_stats()
    print(f"Initial setup:")
    print(f"  Divided government: {separation_stats['divided_government']}")
    print(f"  Executive party: {separation_stats['executive_party']}")
    print(f"  Legislative majority: {separation_stats['legislative_majority_party']}")
    
    # Try to pass legislation that will face opposition
    gridlock_bills = [
        Bill(bill_id=i, ideology=(
            model.random.uniform(-1, 1), 
            model.random.uniform(-1, 1)
        ), salience=0.8) 
        for i in range(10)
    ]
    
    initial_gridlock = model.gridlock_events
    
    for bill in gridlock_bills:
        model.pass_legislation(bill)
    
    final_stats = model.get_system_stats()
    final_separation = model.get_separation_of_powers_stats()
    
    print(f"\nGridlock Results:")
    print(f"  New gridlock events: {final_stats['gridlock_events'] - initial_gridlock}")
    print(f"  Bills vetoed: {final_stats['bills_vetoed']}")
    print(f"  Final veto rate: {final_separation['veto_rate']:.1%}")
    print(f"  Final gridlock rate: {final_separation['gridlock_rate']:.1%}")


def test_committee_agenda_control():
    """Test committee agenda-setting powers in republican system."""
    print("\n=== Testing Committee Agenda Control ===")
    
    model = RepublicanModel(
        num_legislators=18,
        num_constituencies=6,
        num_parties=3,
        num_committees=4,
        committee_size=6,
        committee_gatekeeping_power=0.4,
        seed=42
    )
    
    committee_stats = model.get_committee_stats()
    
    print(f"Committee System:")
    print(f"  Number of committees: {committee_stats['num_committees']}")
    print(f"  Average committee size: {committee_stats['avg_committee_size']:.1f}")
    
    print(f"\nCommittee Details:")
    for committee_detail in committee_stats['committee_details']:
        print(f"  {committee_detail['jurisdiction']} ({committee_detail['policy_area']}):")
        print(f"    Members: {committee_detail['size']}")
        print(f"    Chair: {committee_detail['chair']}")
        print(f"    Party composition: {committee_detail['party_composition']}")


def test_system_comparison():
    """Compare republican vs parliamentary on same parameters."""
    print("\n=== Republican vs Parliamentary Comparison ===")
    
    from institutions.parliamentary import ParliamentaryModel
    
    # Same base parameters
    params = {
        'num_legislators': 15,
        'num_constituencies': 5,
        'num_parties': 3,
        'seed': 42
    }
    
    republican = RepublicanModel(
        discipline_strength=0.4,
        executive_opposition_rate=0.3,
        **params
    )
    
    parliamentary = ParliamentaryModel(
        discipline_strength=0.8,  # Much stronger
        **params
    )
    
    # Test same bills through both systems
    test_bills = [
        Bill(bill_id=i, ideology=(
            republican.random.uniform(-1, 1), 
            republican.random.uniform(-1, 1)
        ), salience=0.5) 
        for i in range(10)
    ]
    
    rep_passed = sum(1 for bill in test_bills if republican.pass_legislation(bill))
    parl_passed = sum(1 for bill in test_bills if parliamentary.pass_legislation(bill))
    
    print(f"Same 10 bills through both systems:")
    print(f"  Republican system: {rep_passed}/10 passed")
    print(f"  Parliamentary system: {parl_passed}/10 passed")
    
    # Compare committee performance
    rep_committee = republican.get_committee_stats()
    parl_committee = parliamentary.get_committee_stats()
    
    print(f"\nCommittee Comparison:")
    print(f"  Republican kill rate: {rep_committee['avg_kill_rate']:.1%}")
    print(f"  Parliamentary kill rate: {parl_committee['avg_kill_rate']:.1%}")
    
    # System-specific features
    rep_stats = republican.get_system_stats()
    parl_stats = parliamentary.get_government_stats()
    
    print(f"\nSystem Features:")
    print(f"  Republican - Vetoes: {rep_stats['bills_vetoed']}, Gridlock: {rep_stats['gridlock_events']}")
    print(f"  Parliamentary - Government: {parl_stats['government_formed']}, Confidence: {parl_stats['confidence_votes_passed']}")


if __name__ == "__main__":
    print("Testing Phase 1.2: Republican/Presidential System")
    print("=" * 60)
    
    test_executive_election()
    test_weak_party_discipline()
    test_executive_veto()
    test_legislative_process()
    test_gridlock_scenarios()
    test_committee_agenda_control()
    test_system_comparison()
    
    print("=" * 60)
    print("All republican system tests completed!")