#!/usr/bin/env python3
"""
Test Phase 2: Legislative Process Realism - Committee System

This script tests the committee system integration with the parliamentary model:
- Committee creation and member assignment
- Bill routing through committees
- Committee amendments and gatekeeping
- Integration with existing parliamentary features
"""

import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from institutions.parliamentary import ParliamentaryModel
from bills.bill import Bill
from agents.committee import CommitteeJurisdiction


def test_committee_creation():
    """Test that committees are created correctly."""
    print("=== Testing Committee Creation ===")
    
    model = ParliamentaryModel(
        num_legislators=15,
        num_constituencies=5,
        num_parties=3,
        num_committees=3,
        committee_size=5,
        seed=42
    )
    
    print(f"Created {len(model.committees)} committees")
    
    for committee in model.committees:
        stats = committee.get_stats()
        print(f"Committee: {stats['jurisdiction']} ({stats['policy_area']})")
        print(f"  Members: {stats['size']}")
        print(f"  Chair: {stats['chair']}")
        print(f"  Party composition: {stats['party_composition']}")
        print()


def test_bill_routing():
    """Test that bills are routed to appropriate committees."""
    print("=== Testing Bill Routing ===")
    
    model = ParliamentaryModel(
        num_legislators=15,
        num_constituencies=5, 
        num_parties=3,
        num_committees=4,
        committee_size=5,
        seed=42
    )
    
    # Create test bills with different ideologies
    test_bills = [
        Bill(bill_id=1, ideology=(0.6, 0.0), salience=0.8),  # Economic conservative -> Finance
        Bill(bill_id=2, ideology=(-0.3, 0.8), salience=0.7),  # Social liberal -> Social Affairs  
        Bill(bill_id=3, ideology=(0.0, -0.5), salience=0.6),  # Conservative social -> Foreign Affairs
        Bill(bill_id=4, ideology=(-0.7, 0.2), salience=0.9),  # Environmental -> Environment
        Bill(bill_id=5, ideology=(0.9, 0.9), salience=0.5),   # Outside all jurisdictions
    ]
    
    for bill in test_bills:
        result = model._route_to_committee(bill)
        print(f"Bill {bill.bill_id} (ideology: {bill.ideology})")
        print(f"  Action: {result['action']}")
        
        # Find which committee should have jurisdiction
        for committee in model.committees:
            if committee.jurisdiction.covers_bill(bill):
                print(f"  Routed to: {committee.jurisdiction.name}")
                break
        else:
            print(f"  No committee jurisdiction")
        print()


def test_committee_amendments():
    """Test committee amendment process."""
    print("=== Testing Committee Amendments ===")
    
    model = ParliamentaryModel(
        num_legislators=12,
        num_constituencies=4,
        num_parties=2,
        num_committees=2,
        committee_size=6,
        seed=42
    )
    
    # Create a bill that might get amended
    original_bill = Bill(bill_id=1, ideology=(0.8, 0.1), salience=0.7)  # Conservative economic
    print(f"Original bill ideology: {original_bill.ideology}")
    
    # Route through committee multiple times to see amendments
    for i in range(5):
        result = model._route_to_committee(original_bill)
        print(f"\nAttempt {i+1}:")
        print(f"  Action: {result['action']}")
        if result['action'] == 'amend':
            amended_bill = result['bill']
            print(f"  Original ideology: {original_bill.ideology}")
            print(f"  Amended ideology: {amended_bill.ideology}")
            original_bill = amended_bill  # Use amended version for next iteration
        elif result['action'] == 'kill':
            print(f"  Bill killed!")
            break


def test_committee_statistics():
    """Test committee statistics tracking."""
    print("=== Testing Committee Statistics ===")
    
    model = ParliamentaryModel(
        num_legislators=15,
        num_constituencies=5,
        num_parties=3,
        num_committees=3,
        committee_size=5,
        committee_gatekeeping_power=0.4,  # Higher kill rate for testing
        seed=42
    )
    
    # Pass several bills through the system
    test_bills = [
        Bill(bill_id=i, ideology=(
            model.random.uniform(-1, 1), 
            model.random.uniform(-1, 1)
        ), salience=0.5) 
        for i in range(20)
    ]
    
    print(f"Passing {len(test_bills)} bills through parliament...")
    
    passed_count = 0
    for bill in test_bills:
        if model.pass_legislation(bill):
            passed_count += 1
    
    print(f"\nResults: {passed_count}/{len(test_bills)} bills passed")
    
    # Get committee statistics
    committee_stats = model.get_committee_stats()
    print(f"\nCommittee System Statistics:")
    print(f"  Committees: {committee_stats['num_committees']}")
    print(f"  Average size: {committee_stats['avg_committee_size']:.1f}")
    print(f"  Bills considered: {committee_stats['total_bills_considered']}")
    print(f"  Bills killed: {committee_stats['total_bills_killed']}")
    print(f"  Amendments made: {committee_stats['total_amendments']}")
    print(f"  Kill rate: {committee_stats['avg_kill_rate']:.2%}")
    print(f"  Amendment rate: {committee_stats['avg_amendment_rate']:.2%}")
    
    print(f"\nIndividual Committee Performance:")
    for committee_detail in committee_stats['committee_details']:
        print(f"  {committee_detail['jurisdiction']}:")
        print(f"    Bills considered: {committee_detail['bills_considered']}")
        print(f"    Approval rate: {committee_detail['approval_rate']:.2%}")
        print(f"    Kill rate: {committee_detail['kill_rate']:.2%}")
        print(f"    Amendment rate: {committee_detail['amendment_rate']:.2%}")


def test_integration_with_parliamentary():
    """Test integration with existing parliamentary features."""
    print("=== Testing Parliamentary Integration ===")
    
    model = ParliamentaryModel(
        num_legislators=20,
        num_constituencies=6,
        num_parties=4,
        num_committees=4,
        committee_size=6,
        confidence_threshold=0.5,
        discipline_strength=0.8,
        seed=42
    )
    
    # Check government formation still works
    gov_stats = model.get_government_stats()
    print(f"Government formed: {gov_stats['government_formed']}")
    print(f"Coalition size: {gov_stats['coalition_size']}")
    print(f"Government party: {gov_stats['government_party']}")
    
    # Run a few simulation steps
    print(f"\nRunning 10 simulation steps...")
    for i in range(10):
        model.step()
    
    # Check final statistics
    final_gov_stats = model.get_government_stats()
    final_committee_stats = model.get_committee_stats()
    
    print(f"\nFinal Results:")
    print(f"  Government still formed: {final_gov_stats['government_formed']}")
    print(f"  Confidence votes passed: {final_gov_stats['confidence_votes_passed']}")
    print(f"  Confidence votes failed: {final_gov_stats['confidence_votes_failed']}")
    print(f"  Committee bills considered: {final_committee_stats['total_bills_considered']}")


if __name__ == "__main__":
    print("Testing Phase 2: Legislative Process Realism - Committee System")
    print("=" * 60)
    
    test_committee_creation()
    test_bill_routing() 
    test_committee_amendments()
    test_committee_statistics()
    test_integration_with_parliamentary()
    
    print("=" * 60)
    print("All tests completed!")