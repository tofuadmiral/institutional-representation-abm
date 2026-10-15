"""Offline, prospectively specified reciprocal-exchange opportunity structures.

These are theory-selected games, not a population sample or a guaranteed effect.
No model calls, credentials, files or mutable global state are used here.
"""
from itertools import combinations

from paper3 import coalition_contracts as game
from paper3 import coalition_jurisdiction_design as display


SEED_BASES=(352000,352100,353000,353100)  # profile x seed block
EX_ANTE_EXPOSED=((4,5,6),(6,))


def fixtures():
    specs=(
        ("reciprocal_four",[(10,-4),(8,-3),(-4,10),(-3,8),(-5,-3),(-4,-5),(-6,-2)],2),
        ("overlapping_six",[(10,-3),(9,-4),(8,-2),(-3,10),(-2,9),(-4,8),(-8,-7)],2),
    )
    out=[]
    for name,pairs,alternative in specs:
        p=dict(id=name,proposer=0,utilities=[
            dict(A0=a,A1=alternative,B0=b,B1=alternative) for a,b in pairs])
        game.validate_profile(p);out.append(p)
    return out


def opportunities(profile):
    """Exact finite-menu opportunity checks; these do not predict agent choices."""
    game.validate_profile(profile)
    rows=profile["utilities"]
    potential=[i for i,row in enumerate(rows) if row["A0"]+row["B0"]>0]
    eligible=[list(c) for c in combinations(potential,4)]
    pivotal=[]
    for c in eligible:
        for defector in c:
            if rows[defector]["B0"]>=0:continue
            # Other signers honor the second promise; nonmembers vote for a
            # strictly positive marginal project. The negative-marginal member
            # can then be causally pivotal to that *fixed requested-ballot* count.
            yes=sum(rows[i]["B0"]>0 for i in game.ACTORS if i not in c)+3
            if yes==3:pivotal.append(dict(coalition=c,defector=defector))
    return dict(positive_A0=sum(row["A0"]>0 for row in rows),
        positive_B0=sum(row["B0"]>0 for row in rows),
        package_positive=potential,
        inclusive_alternative=[row["A1"]+row["B1"] for row in rows],
        outsider_package_loss=[i for i,row in enumerate(rows) if row["A0"]+row["B0"]<0],
        eligible_coalitions=eligible,pivotal_second_vote_opportunities=pivotal)


def schedule(seed_bases=SEED_BASES):
    game.require(len(seed_bases)==4 and all(type(s) is int and s>=0 for s in seed_bases),
                 "four fresh seed bases")
    ranges=[set(range(s,s+30)) for s in seed_bases]
    game.require(sum(map(len,ranges))==len(set().union(*ranges)),"overlapping seed ranges")
    result=[]
    for profile_index in range(2):
        for form in range(2):
            for repeat in range(2):
                block=profile_index*4+form*2+repeat
                arms=game.ARMS[block%3:]+game.ARMS[:block%3]
                for arm in arms:
                    result.append(dict(id=f"exchange-{profile_index}-form-{form}-seed-{repeat}-{arm}",
                        fixture_index=profile_index,form=form,repeat=repeat,block=block,
                        arm=arm,seed_base=seed_bases[profile_index*2+repeat]))
    game.require(len(result)==24,"24 assignment schedule")
    return result


display_profile=display.display_profile
maps=display.maps
canonical_utilities=display.canonical_utilities
canonical_offer=display.canonical_offer
labelled_messages=display.labelled_messages


def episode(profile,arm,ask):
    def labelled_ask(actor,stage,messages,index):
        return ask(actor,stage,labelled_messages(messages),index)
    return game.episode(profile,arm,labelled_ask)
