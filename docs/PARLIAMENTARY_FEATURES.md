# Parliamentary System Implementation

## Overview

This document describes the parliamentary system features implemented in Phase 1.1 of the institutional representation ABM project.

## Core Features

### 1. Government Formation

The parliamentary system now implements realistic government formation:

- **Single Party Majority**: If one party has >50% of seats, it forms government alone
- **Coalition Government**: If no majority, largest party seeks coalition with next largest
- **Prime Minister Selection**: Randomly chosen from the government party's legislators
- **Government State Tracking**: Tracks whether government is formed and coalition composition

### 2. Confidence Votes

Parliamentary systems feature confidence votes that can bring down governments:

- **Confidence Matters**: 30% of bills are treated as confidence votes
- **Government Survival**: Government needs >50% support to survive confidence votes
- **Government Falls**: Failed confidence votes trigger new government formation
- **Vote Tracking**: System tracks confidence votes passed/failed over time

### 3. Party Discipline

Strong party discipline is a hallmark of parliamentary systems:

- **Government Discipline**: Government party members vote with party line 80% of the time (configurable)
- **Opposition Discipline**: Opposition parties vote against government ~56% of the time (70% of 80%)
- **Personal Voting**: Remaining votes based on legislator's personal ideology
- **Configurable Strength**: Discipline strength can be adjusted (0.0 = no discipline, 1.0 = perfect discipline)

### 4. Coalition Building

Multi-party coalitions are supported:

- **Automatic Formation**: System automatically attempts coalition building
- **Coalition Tracking**: Tracks which parties are in government coalition
- **Coalition Voting**: All coalition parties benefit from government discipline

## Enhanced Metrics

### Model-Level Metrics

New parliamentary-specific metrics added to data collection:

- `government_formed`: Whether a stable government exists
- `coalition_size`: Number of parties in government coalition  
- `confidence_votes_passed`: Running total of successful confidence votes
- `confidence_votes_failed`: Running total of failed confidence votes

### Representation Quality Metrics

New metrics to measure representational performance:

- `avg_legislator_constituency_distance`: Average ideological distance between legislators and their constituencies
- `representation_inequality`: Variance in representation quality across constituencies

### Agent-Level Metrics

Enhanced agent tracking:

- `ideology_x`, `ideology_y`: Agent positions in 2D ideological space
- `is_in_government`: Whether legislator is part of government coalition
- `constituency_distance`: Ideological distance between legislator and constituency

## Usage Examples

### Basic Parliamentary System

```python
from institutions.parliamentary import ParliamentaryModel

# Create parliamentary system
model = ParliamentaryModel(
    num_legislators=15,
    num_constituencies=5, 
    num_parties=3,
    confidence_threshold=0.5,  # 50% needed for confidence
    discipline_strength=0.8,   # 80% party discipline
    seed=42
)

# Check government formation
stats = model.get_government_stats()
print(f"Government formed: {stats['government_formed']}")
print(f"Coalition size: {stats['coalition_size']}")
```

### Testing Legislation

```python
from bills.bill import Bill

# Create a bill
bill = Bill(bill_id=1, ideology=(0.0, 0.0), salience=0.8)

# Pass through parliament
passed = model.pass_legislation(bill)
print(f"Bill passed: {passed}")
```

### Running Simulation

```python
# Run simulation steps
for step in range(10):
    model.step()

# Analyze results
model_data = model.datacollector.get_model_vars_dataframe()
print("Government stability:", model_data['government_formed'].mean())
print("Average representation distance:", model_data['avg_legislator_constituency_distance'].mean())
```

## Configuration Parameters

- `confidence_threshold`: Fraction of votes needed for confidence (default: 0.5)
- `discipline_strength`: How often party members follow party line (default: 0.8)
- `num_legislators`: Total number of legislators
- `num_parties`: Number of political parties
- `num_constituencies`: Number of electoral districts

## Testing

Run the parliamentary system tests:

```bash
cd institutional-representation-abm
PYTHONPATH=. python3 experiments/test_parliamentary.py
```

This will test:
- Government formation with different party configurations
- Legislation passage with varying ideological positions
- Confidence vote mechanics
- Party discipline effects
- Representation quality measurement

## Next Steps

Phase 1.2 will implement the republican/presidential system with:
- Separation of powers
- Committee systems  
- Individual legislator autonomy
- Fixed terms and gridlock scenarios

Phase 1.3 will create comparative experiments between parliamentary and republican systems.