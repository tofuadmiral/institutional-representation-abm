from __future__ import annotations

from institutions.parliamentary import ParliamentaryModel
from bills.bill import Bill


def test_parliamentary_features(steps: int = 10) -> None:
    """
    Test parliamentary system specific features including:
    - Government formation
    - Confidence votes  
    - Party discipline
    - Coalition building
    """
    print("=== Parliamentary System Feature Test ===\n")
    
    # Create model with multiple parties to test coalition building
    model = ParliamentaryModel(
        num_legislators=15,
        num_constituencies=5,
        num_parties=3,  # Multiple parties for coalition scenarios
        confidence_threshold=0.5,
        discipline_strength=0.8,
        seed=42,
    )
    
    print("Initial Government Formation:")
    gov_stats = model.get_government_stats()
    print(f"  Government Formed: {gov_stats['government_formed']}")
    print(f"  Leading Party: {gov_stats['government_party']}")
    print(f"  Coalition Size: {gov_stats['coalition_size']}")
    print(f"  Prime Minister ID: {gov_stats['prime_minister_id']}")
    print()
    
    # Test legislation passage
    print("Testing Legislation Passage:")
    test_bill = Bill(
        bill_id=1,
        ideology=(0.0, 0.0),  # Centrist bill
        salience=0.8
    )
    
    result = model.pass_legislation(test_bill)
    print(f"  Bill 1 (Centrist) Passed: {result}")
    
    # Test with extreme bill
    extreme_bill = Bill(
        bill_id=2,
        ideology=(1.0, 1.0),  # Extreme bill
        salience=0.9
    )
    
    result2 = model.pass_legislation(extreme_bill)
    print(f"  Bill 2 (Extreme) Passed: {result2}")
    print()
    
    # Run simulation steps
    print(f"Running {steps} simulation steps...")
    for step in range(steps):
        model.step()
        
        # Print government stats every few steps
        if step % 3 == 0:
            stats = model.get_government_stats()
            print(f"  Step {step}: Confidence votes passed/failed: {stats['confidence_votes_passed']}/{stats['confidence_votes_failed']}")
    
    print()
    
    # Final analysis
    print("Final Results:")
    model_df = model.datacollector.get_model_vars_dataframe()
    agent_df = model.datacollector.get_agent_vars_dataframe()
    
    print("Government Stability Over Time:")
    print(model_df[['government_formed', 'coalition_size', 'confidence_votes_passed', 'confidence_votes_failed']].tail())
    
    print("\nRepresentation Quality:")
    print(model_df[['avg_legislator_constituency_distance', 'representation_inequality']].tail())
    
    print("\nAgent Summary (Legislators only):")
    legislator_df = agent_df[agent_df['agent_type'] == 'LegislatorAgent']
    print(f"  Total Legislators: {len(legislator_df.index.get_level_values('AgentID').unique())}")
    
    if not legislator_df.empty:
        print("  Government vs Opposition:")
        final_step = legislator_df.index.get_level_values('Step').max()
        final_legislators = legislator_df.loc[final_step]
        gov_count = final_legislators['is_in_government'].sum()
        total_legislators = len(final_legislators)
        print(f"    Government: {gov_count}/{total_legislators} legislators")
        print(f"    Average constituency distance: {final_legislators['constituency_distance'].mean():.3f}")


def compare_discipline_levels() -> None:
    """
    Compare parliamentary systems with different levels of party discipline.
    """
    print("\n=== Party Discipline Comparison ===\n")
    
    discipline_levels = [0.5, 0.8, 0.95]
    
    for discipline in discipline_levels:
        print(f"Testing discipline strength: {discipline}")
        
        model = ParliamentaryModel(
            num_legislators=12,
            num_constituencies=4,
            num_parties=2,
            discipline_strength=discipline,
            seed=42
        )
        
        # Run a few steps
        for _ in range(5):
            model.step()
        
        # Get final stats
        final_data = model.datacollector.get_model_vars_dataframe().iloc[-1]
        print(f"  Confidence votes passed: {final_data['confidence_votes_passed']}")
        print(f"  Government stability: {final_data['government_formed']}")
        print(f"  Representation distance: {final_data['avg_legislator_constituency_distance']:.3f}")
        print()


if __name__ == "__main__":
    test_parliamentary_features()
    compare_discipline_levels()