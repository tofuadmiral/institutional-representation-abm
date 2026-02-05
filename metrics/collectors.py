from __future__ import annotations

from typing import Callable, Dict, Any

from mesa.datacollection import DataCollector


def default_model_reporters() -> Dict[str, Callable[[Any], Any]]:
    """
    Model-level metrics tracked across institutional variants.

    These are deliberately simple aggregate indicators that help verify that
    runs are reproducible and that institutional subclasses behave comparably.
    """

    return {
        "schedule_time": lambda m: m.schedule.time,
        "num_legislators": lambda m: m.num_legislators,
        "num_constituencies": lambda m: m.num_constituencies,
        "num_parties": lambda m: m.num_parties,
        # Parliamentary-specific metrics (safe for other models)
        "government_formed": lambda m: getattr(m, 'government_formed', None),
        "coalition_size": lambda m: len(getattr(m, 'government_coalition', [])),
        "confidence_votes_passed": lambda m: getattr(m, 'confidence_votes_passed', 0),
        "confidence_votes_failed": lambda m: getattr(m, 'confidence_votes_failed', 0),
        # Republican-specific metrics (safe for other models)
        "executive_party": lambda m: getattr(m, 'executive_party', None),
        "bills_vetoed": lambda m: getattr(m, 'bills_vetoed', 0),
        "gridlock_events": lambda m: getattr(m, 'gridlock_events', 0),
        "divided_government": _check_divided_government,
        "veto_rate": _calculate_veto_rate,
        # Representation quality metrics
        "avg_legislator_constituency_distance": _avg_legislator_constituency_distance,
        "representation_inequality": _representation_inequality,
        # Committee system metrics
        "num_committees": lambda m: len(getattr(m, 'committees', [])),
        "total_bills_in_committee": lambda m: sum(c.bills_considered for c in getattr(m, 'committees', [])),
        "total_bills_killed_by_committees": lambda m: sum(c.bills_killed for c in getattr(m, 'committees', [])),
        "total_committee_amendments": lambda m: sum(c.amendments_made for c in getattr(m, 'committees', [])),
        "committee_kill_rate": _committee_kill_rate,
        "committee_amendment_rate": _committee_amendment_rate,
    }


def _avg_legislator_constituency_distance(model) -> float:
    """
    Calculate average ideological distance between legislators and their constituencies.
    
    Lower values indicate better representational congruence.
    """
    if not hasattr(model, 'legislators') or not hasattr(model, 'constituencies'):
        return 0.0
        
    distances = []
    for legislator in model.legislators:
        if legislator.constituency_id in model.constituencies:
            constituency = model.constituencies[legislator.constituency_id]
            # Euclidean distance in 2D ideology space
            dist = ((legislator.ideology[0] - constituency.ideology[0])**2 + 
                   (legislator.ideology[1] - constituency.ideology[1])**2)**0.5
            distances.append(dist)
    
    return sum(distances) / len(distances) if distances else 0.0


def _representation_inequality(model) -> float:
    """
    Measure inequality in representation quality across constituencies.
    
    Higher values indicate more unequal representation.
    Uses variance in legislator-constituency distances.
    """
    if not hasattr(model, 'legislators') or not hasattr(model, 'constituencies'):
        return 0.0
        
    distances = []
    for legislator in model.legislators:
        if legislator.constituency_id in model.constituencies:
            constituency = model.constituencies[legislator.constituency_id]
            dist = ((legislator.ideology[0] - constituency.ideology[0])**2 + 
                   (legislator.ideology[1] - constituency.ideology[1])**2)**0.5
            distances.append(dist)
    
    if len(distances) < 2:
        return 0.0
        
    # Calculate variance as inequality measure
    mean_dist = sum(distances) / len(distances)
    variance = sum((d - mean_dist)**2 for d in distances) / len(distances)
    return variance


def default_agent_reporters() -> Dict[str, Callable[[Any], Any]]:
    """
    Agent-level metrics tracked for basic inspection of the population.

    Enhanced to capture representational relationships and behavior.
    """

    return {
        "agent_type": lambda a: type(a).__name__,
        "ideology_x": lambda a: getattr(a, 'ideology', (None, None))[0],
        "ideology_y": lambda a: getattr(a, 'ideology', (None, None))[1], 
        "party_id": lambda a: getattr(a, 'party_id', None),
        "constituency_id": lambda a: getattr(a, 'constituency_id', None),
        "population": lambda a: getattr(a, 'population', None),  # For constituencies
        "is_in_government": lambda a: _is_in_government(a),
        "constituency_distance": lambda a: _get_constituency_distance(a),
    }


def _is_in_government(agent) -> bool:
    """Check if a legislator is part of the current government coalition."""
    if not hasattr(agent, 'party_id') or not hasattr(agent, 'model'):
        return False
    
    model = agent.model
    if hasattr(model, 'government_coalition'):
        return agent.party_id in model.government_coalition
    return False


def _get_constituency_distance(agent) -> float:
    """Get ideological distance between legislator and their constituency."""
    if not hasattr(agent, 'constituency_id') or not hasattr(agent, 'model') or not hasattr(agent, 'ideology'):
        return 0.0
    
    model = agent.model
    if hasattr(model, 'constituencies') and agent.constituency_id in model.constituencies:
        constituency = model.constituencies[agent.constituency_id]
        dist = ((agent.ideology[0] - constituency.ideology[0])**2 + 
               (agent.ideology[1] - constituency.ideology[1])**2)**0.5
        return dist
    return 0.0


def _committee_kill_rate(model) -> float:
    """Calculate the rate at which committees kill bills."""
    committees = getattr(model, 'committees', [])
    if not committees:
        return 0.0
    
    total_considered = sum(c.bills_considered for c in committees)
    total_killed = sum(c.bills_killed for c in committees)
    
    return (total_killed / total_considered) if total_considered > 0 else 0.0


def _committee_amendment_rate(model) -> float:
    """Calculate the rate at which committees amend bills."""
    committees = getattr(model, 'committees', [])
    if not committees:
        return 0.0
    
    total_considered = sum(c.bills_considered for c in committees)  
    total_amended = sum(c.amendments_made for c in committees)
    
    return (total_amended / total_considered) if total_considered > 0 else 0.0


def _check_divided_government(model) -> bool:
    """Check if government is divided between executive and legislative branches."""
    executive_party = getattr(model, 'executive_party', None)
    if executive_party is None:
        return False
    
    # Count legislative party seats
    party_seats = {}
    for agent in getattr(model, 'schedule', []):
        if hasattr(agent, 'agents'):
            for a in agent.agents:
                if hasattr(a, 'party_id') and a.party_id is not None:
                    party_seats[a.party_id] = party_seats.get(a.party_id, 0) + 1
    
    if not party_seats:
        return False
        
    legislative_majority = max(party_seats.keys(), key=lambda k: party_seats[k])
    return executive_party != legislative_majority


def _calculate_veto_rate(model) -> float:
    """Calculate the rate at which executive vetoes legislation."""
    bills_passed = getattr(model, 'bills_passed', 0)
    bills_vetoed = getattr(model, 'bills_vetoed', 0)
    
    total_bills = bills_passed + bills_vetoed
    return (bills_vetoed / total_bills) if total_bills > 0 else 0.0


def build_default_datacollector() -> DataCollector:
    """
    Construct a DataCollector with baseline model and agent reporters.

    Institutional subclasses can reuse or extend this configuration without
    needing to re-specify common metrics.
    """

    return DataCollector(
        model_reporters=default_model_reporters(),
        agent_reporters=default_agent_reporters(),
    )


