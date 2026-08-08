"""Generate synthetic production traces for the trail-report-tagging example.

Emits traces.jsonl (logs of a legacy tagging service) and job_description.json from one
taxonomy, so the reports and the prompt describing the taxonomy cannot drift apart.

Every trace is built backwards: a ground-truth tag set is sampled first, then a report is
written that states exactly those conditions. Multi-label "does this report support this
tag" is otherwise a judgment call, and ambiguous labels would cap the teacher, which caps
everything downstream.
"""

import argparse
import json
import random
from pathlib import Path

# Ordered families. Canonical output order is taxonomy order, which is this order.
FAMILIES = ["IMPASSABLE", "OBSTRUCTION", "SEASONAL", "COMFORT"]

# code, family, definition (goes verbatim into the prompt), report phrasings.
TAXONOMY = [
    # --- IMPASSABLE: the trail cannot be travelled safely at this point ---
    {
        "code": "BRIDGE_OUT",
        "family": "IMPASSABLE",
        "definition": "a built crossing is destroyed, missing, or unusable",
        "phrases": [
            "the footbridge at the lower crossing is gone entirely",
            "the bridge decking has collapsed and there is no way over",
            "the span over the gorge is down, nothing left but the abutments",
            "the plank bridge below the junction has washed away",
        ],
    },
    {
        "code": "FORD_UNSAFE",
        "family": "IMPASSABLE",
        "definition": "an unbridged crossing cannot be crossed safely at present",
        "phrases": [
            "the ford is pushing too hard to cross on foot",
            "we turned back at the unbridged crossing, it is not safe to wade",
            "the creek crossing is chest deep and moving fast, do not attempt it",
            "nobody in our group could find a safe line across the ford",
        ],
    },
    {
        "code": "WASHOUT_MAJOR",
        "family": "IMPASSABLE",
        "definition": (
            "the tread is gone to a slide or flood scar and there is no safe way across "
            "the scar"
        ),
        "phrases": [
            "a slide has taken out the tread completely with no safe way across the scar",
            "the trail is gone into a washout scar, we could not get across it",
            "flood scour removed the entire bench and there is no line across",
        ],
    },
    {
        "code": "ROCKFALL_ACTIVE",
        "family": "IMPASSABLE",
        "definition": "rock is actively releasing onto the trail",
        "phrases": [
            "rock was coming down onto the trail while we watched",
            "the gully above the traverse is actively shedding rock",
            "we heard and saw repeated rockfall crossing the corridor",
        ],
    },
    {
        "code": "SNOW_BRIDGE_THIN",
        "family": "IMPASSABLE",
        "definition": "a snow bridge over water or a void will not hold weight",
        "phrases": [
            "the snow bridge over the creek is hollowed out and will not hold",
            "the remaining snow bridge collapsed under a pole probe",
            "the snow span over the void is rotten through",
        ],
    },
    {
        "code": "BURN_CLOSURE",
        "family": "IMPASSABLE",
        "definition": "the trail lies inside a posted or active burn closure",
        "phrases": [
            "the segment is inside a posted burn closure",
            "closure signs for the fire area are up across the trail",
            "the corridor is shut for the active burn area",
        ],
    },
    {
        "code": "TREAD_COLLAPSE",
        "family": "IMPASSABLE",
        "definition": (
            "the tread has fallen away on exposed sidehill, leaving no footing at all"
        ),
        "phrases": [
            "the tread has fallen off the sidehill leaving no footing whatsoever",
            "the bench collapsed on the exposed traverse, there is nothing to stand on",
            "the outslope gave way entirely above the drop, no footing remains",
        ],
    },
    {
        "code": "AVALANCHE_DEBRIS",
        "family": "IMPASSABLE",
        "definition": "an avalanche deposit blocks the corridor",
        "phrases": [
            "avalanche debris fills the corridor with piled timber and snow",
            "a slide path has dumped a deposit across the trail",
            "the runout is choked with avalanche debris",
        ],
    },
    # --- OBSTRUCTION: passable, but the way itself is degraded ---
    {
        "code": "BLOWDOWN_HEAVY",
        "family": "OBSTRUCTION",
        "definition": (
            "downed trees must be climbed over or bushwhacked around (as opposed to "
            "stepped over)"
        ),
        "phrases": [
            "there is enough blowdown that you are climbing over trunks",
            "downed timber forces you to scramble over and around it repeatedly",
            "the deadfall is stacked high enough that you have to go over the top",
        ],
    },
    {
        "code": "BLOWDOWN_LIGHT",
        "family": "OBSTRUCTION",
        "definition": (
            "downed trees can be stepped over without leaving the tread (as opposed to "
            "climbed over)"
        ),
        "phrases": [
            "a few downed trees but all of them step-overs",
            "some deadfall across the tread, easy to step over",
            "scattered small trunks down, none of them a problem to step across",
        ],
    },
    {
        "code": "OVERGROWN",
        "family": "OBSTRUCTION",
        "definition": "brush encroaches enough to hide the tread",
        "phrases": [
            "brush has closed in enough to hide the tread underfoot",
            "the corridor is grown over and you are feeling for the trail",
            "alder is over head height and you cannot see where you are stepping",
        ],
    },
    {
        "code": "TREAD_EROSION",
        "family": "OBSTRUCTION",
        "definition": (
            "rutting or gullying has narrowed the tread, but it remains walkable"
        ),
        "phrases": [
            "the tread is rutted and narrow but still walkable",
            "gullying has cut the trail down to a narrow walkable strip",
            "erosion has pinched the tread though you can still walk it",
        ],
    },
    {
        "code": "CAIRN_MISSING",
        "family": "OBSTRUCTION",
        "definition": "route-marking cairns are absent where the route needs them",
        "phrases": [
            "the cairns across the slabs are gone where you need them",
            "route markers on the open rock are missing",
            "no cairns left through the boulder section",
        ],
    },
    {
        "code": "SIGN_DAMAGED",
        "family": "OBSTRUCTION",
        "definition": "signage is broken, illegible, or points the wrong way",
        "phrases": [
            "the junction sign is snapped off at the post",
            "the signboard is illegible and one arm points the wrong way",
            "the directional sign at the fork is broken",
        ],
    },
    {
        "code": "BLAZE_FADED",
        "family": "OBSTRUCTION",
        "definition": "painted or cut blazes are no longer visible",
        "phrases": [
            "the painted blazes have weathered away to nothing",
            "blazes on the trees are no longer visible",
            "the cut blazes have healed over and cannot be picked out",
        ],
    },
    {
        "code": "REROUTE_UNMARKED",
        "family": "OBSTRUCTION",
        "definition": "an unofficial path diverges from the route with no marking",
        "phrases": [
            "a user path splits off with nothing marking which way is the trail",
            "an unofficial reroute leaves the corridor unmarked",
            "a beaten side path diverges and there is no sign saying which to take",
        ],
    },
    {
        "code": "GATE_STUCK",
        "family": "OBSTRUCTION",
        "definition": "a stock gate or stile cannot be operated",
        "phrases": [
            "the stock gate will not open, the latch is seized",
            "the stile is jammed and unusable",
            "the pasture gate is wired shut and cannot be worked",
        ],
    },
    {
        "code": "LADDER_DAMAGED",
        "family": "OBSTRUCTION",
        "definition": "a fixed ladder or step structure is compromised but still usable",
        "phrases": [
            "the fixed ladder has a cracked rung but still goes",
            "the ladder is loose at the top though usable with care",
            "one step on the fixed ladder is broken, passable carefully",
        ],
    },
    {
        "code": "CABLE_LOOSE",
        "family": "OBSTRUCTION",
        "definition": "a fixed handline or cable is no longer taut",
        "phrases": [
            "the fixed handline is slack",
            "the cable on the traverse has gone loose",
            "the handline no longer holds tension",
        ],
    },
    {
        "code": "BOARDWALK_BROKEN",
        "family": "OBSTRUCTION",
        "definition": "puncheon or boardwalk decking is failing underfoot",
        "phrases": [
            "boardwalk planks are rotting through underfoot",
            "the puncheon decking is breaking as you step on it",
            "several boardwalk boards are soft and giving way",
        ],
    },
    {
        "code": "STEPS_UNDERMINED",
        "family": "OBSTRUCTION",
        "definition": "constructed steps have washed out beneath",
        "phrases": [
            "the stone steps are undermined and hollow underneath",
            "the constructed steps have washed out below the treads",
            "the timber steps are floating with the fill gone from under them",
        ],
    },
    {
        "code": "DRAIN_BLOCKED",
        "family": "OBSTRUCTION",
        "definition": (
            "a drainage structure such as a water bar or culvert is clogged; use this "
            "for a failed structure, not for water on the tread with no structure at "
            "fault"
        ),
        "phrases": [
            "the water bars are packed solid with debris",
            "the culvert is plugged and backing up",
            "every drain along the pitch is clogged with duff",
        ],
    },
    # --- SEASONAL: conditions that will change with the season ---
    {
        "code": "SNOW_PATCH",
        "family": "SEASONAL",
        "definition": (
            "lingering snow that can be crossed or walked around (as opposed to "
            "continuous cover)"
        ),
        "phrases": [
            "a few lingering snow patches, all easy to walk around",
            "isolated snow patches remain and you can step around them",
            "patchy old snow in the shaded bends, avoidable",
        ],
    },
    {
        "code": "SNOW_CONTINUOUS",
        "family": "SEASONAL",
        "definition": (
            "snow covers the route continuously and route-finding is needed (as opposed "
            "to isolated patches)"
        ),
        "phrases": [
            "snow is continuous above the basin and you are route-finding",
            "unbroken snow cover the whole way up, no tread visible",
            "continuous snow with no trail to follow, navigation required",
        ],
    },
    {
        "code": "ICE_PATCH",
        "family": "SEASONAL",
        "definition": "verglas or ice on the tread",
        "phrases": [
            "verglas on the tread in the shaded corners",
            "clear ice over the rock steps",
            "icy patches on the trail where the seeps run",
        ],
    },
    {
        "code": "MUD_DEEP",
        "family": "SEASONAL",
        "definition": "mud swallows boots over a sustained stretch",
        "phrases": [
            "boot-swallowing mud for a long sustained stretch",
            "deep mud that takes you in past the ankle for a good distance",
            "sustained bog where every step goes in deep",
        ],
    },
    {
        "code": "POSTHOLING",
        "family": "SEASONAL",
        "definition": "soft snow collapses underfoot",
        "phrases": [
            "the snow is soft and you are postholing through it",
            "we broke through to the knee with every step in the afternoon snow",
            "the pack has gone soft and collapses underfoot",
        ],
    },
    {
        "code": "WATER_LOW",
        "family": "SEASONAL",
        "definition": (
            "seasonal water sources are dry or nearly dry; this is about sources, never "
            "about a creek being easy to cross"
        ),
        "phrases": [
            "the seasonal sources along the ridge are dry",
            "the marked springs are down to nothing",
            "the seasonal water holes have gone dry",
        ],
    },
    {
        "code": "WATER_HIGH",
        "family": "SEASONAL",
        "definition": (
            "creeks are running high but are still crossable; a crossing that is not "
            "safe is FORD_UNSAFE instead"
        ),
        "phrases": [
            "the creeks are running high but all still crossable",
            "high water in the drainages, wet feet but fine to cross",
            "flows are up though every crossing still goes",
        ],
    },
    {
        "code": "RUNOFF_ON_TREAD",
        "family": "SEASONAL",
        "definition": (
            "melt or rainwater runs down the trail itself with no drainage structure at "
            "fault; a clogged structure is DRAIN_BLOCKED instead"
        ),
        "phrases": [
            "meltwater is running straight down the trail",
            "the tread is carrying water down the fall line",
            "runoff has turned the trail into a streambed",
        ],
    },
    {
        "code": "BLOWDOWN_SNOWLOAD",
        "family": "SEASONAL",
        "definition": (
            "living trees are bent over the trail under snow load; fallen trees are the "
            "BLOWDOWN tags instead"
        ),
        "phrases": [
            "living saplings are bent right over the trail under snow load",
            "green trees are arched across the corridor weighted with snow",
            "snow load has bowed the standing brush over the tread",
        ],
    },
    {
        "code": "CORNICE_PRESENT",
        "family": "SEASONAL",
        "definition": "a ridge cornice overhangs near the route",
        "phrases": [
            "a cornice is still hanging over the ridge near the route",
            "corniced edge along the crest above the trail",
            "the ridge carries an overhanging cornice by the route",
        ],
    },
    {
        "code": "SPRING_SILTED",
        "family": "SEASONAL",
        "definition": (
            "a developed spring runs cloudy or silty; water that is clear but tastes bad "
            "is WATER_TASTE_POOR instead"
        ),
        "phrases": [
            "the developed spring is running cloudy with silt",
            "the piped spring is throwing sediment",
            "the spring box is silted and the water comes out murky",
        ],
    },
    {
        "code": "THAW_UNSTABLE",
        "family": "SEASONAL",
        "definition": "freeze-thaw has made slopes or tread unreliable",
        "phrases": [
            "freeze-thaw has left the slope unreliable underfoot",
            "the tread is heaving from the thaw cycle and gives way",
            "thaw has loosened the whole slope, nothing holds",
        ],
    },
    {
        "code": "LEAF_COVER_DEEP",
        "family": "SEASONAL",
        "definition": "fallen leaves hide the tread and its footing",
        "phrases": [
            "deep leaf litter is hiding the tread and whatever is under it",
            "the trail is buried in leaves and you cannot see your footing",
            "fallen leaves cover the tread completely",
        ],
    },
    {
        "code": "TICKS_ACTIVE",
        "family": "SEASONAL",
        "definition": "ticks are active in seasonal numbers",
        "phrases": [
            "ticks are out in numbers, we pulled several off",
            "heavy tick activity through the grassy sections",
            "picked up ticks repeatedly along the lower trail",
        ],
    },
    # --- COMFORT: affects the experience, not the passage ---
    {
        "code": "BUG_PRESSURE",
        "family": "COMFORT",
        "definition": "mosquitoes or flies are bad enough to affect the trip",
        "phrases": [
            "mosquitoes were brutal the entire way",
            "the flies were bad enough to keep us moving through lunch",
            "bugs were relentless in the timber",
        ],
    },
    {
        "code": "CROWDING_HIGH",
        "family": "COMFORT",
        "definition": "more parties are present than the corridor comfortably holds",
        "phrases": [
            "far more parties out than the trail comfortably holds",
            "we were passing groups constantly, it felt packed",
            "steady stream of hikers the whole way, very busy",
        ],
    },
    {
        "code": "NOISE_ROAD",
        "family": "COMFORT",
        "definition": "road or motor noise is audible along the trail",
        "phrases": [
            "highway noise carries the whole first stretch",
            "you can hear traffic most of the way along",
            "motor noise from the road is audible throughout",
        ],
    },
    {
        "code": "SHADE_SPARSE",
        "family": "COMFORT",
        "definition": "a sustained stretch of the corridor has little tree cover",
        "phrases": [
            "the long middle stretch has almost no tree cover",
            "very little shade for a sustained section",
            "the corridor is open with no canopy for a long way",
        ],
    },
    {
        "code": "WATER_CARRY_LONG",
        "family": "COMFORT",
        "definition": (
            "the distance between available water sources requires carrying; this is "
            "about how far apart sources are, not about sources being dry"
        ),
        "phrases": [
            "the sources are far enough apart that you have to carry",
            "long stretch between water, plan on carrying it",
            "sources are widely spaced and you will be carrying water",
        ],
    },
    {
        "code": "CAMP_SITES_FULL",
        "family": "COMFORT",
        "definition": "established campsites are all occupied",
        "phrases": [
            "every established site was taken",
            "the designated camps were all occupied by evening",
            "no open sites left at the established camps",
        ],
    },
    {
        "code": "CAMP_SITES_TRASHED",
        "family": "COMFORT",
        "definition": "established campsites are littered or damaged",
        "phrases": [
            "the established sites are littered and beaten down",
            "trash left through the camps and the vegetation is wrecked",
            "the camps are in poor shape, litter everywhere",
        ],
    },
    {
        "code": "PRIVY_CLOSED",
        "family": "COMFORT",
        "definition": "a privy is locked, full, or removed",
        "phrases": [
            "the privy is locked shut",
            "the toilet at the camp has been removed",
            "the privy is full and closed off",
        ],
    },
    {
        "code": "WATER_TASTE_POOR",
        "family": "COMFORT",
        "definition": (
            "potable water is unpleasant but usable; cloudy or silty spring water is "
            "SPRING_SILTED instead"
        ),
        "phrases": [
            "the water is clear but tastes strongly of iron",
            "water runs clear but has an off taste to it",
            "the tap water is drinkable but unpleasant",
        ],
    },
    {
        "code": "FIRE_RING_ILLEGAL",
        "family": "COMFORT",
        "definition": "user-built fire rings are present where fires are not allowed",
        "phrases": [
            "user-built fire rings in the no-fire zone",
            "fresh fire rings built where fires are prohibited",
            "someone has built rings above the fire closure line",
        ],
    },
    {
        "code": "PARKING_FULL",
        "family": "COMFORT",
        "definition": "trailhead parking is at capacity",
        "phrases": [
            "the trailhead lot was full early",
            "parking was overflowing onto the road",
            "no spaces left at the trailhead",
        ],
    },
    {
        "code": "DOG_OFF_LEASH",
        "family": "COMFORT",
        "definition": "off-leash dogs are present where they are prohibited",
        "phrases": [
            "several off-leash dogs where leashes are required",
            "dogs running loose despite the leash rule",
            "off-leash dogs on the trail in the leash-required section",
        ],
    },
]

# Near-miss partners. The legacy service confuses these, and they are the pairs whose
# discriminator lives only in the stipulated definition.
NEAR_MISSES = {
    "WATER_LOW": "WATER_CARRY_LONG",
    "WATER_CARRY_LONG": "WATER_LOW",
    "WATER_HIGH": "FORD_UNSAFE",
    "FORD_UNSAFE": "WATER_HIGH",
    "DRAIN_BLOCKED": "RUNOFF_ON_TREAD",
    "RUNOFF_ON_TREAD": "DRAIN_BLOCKED",
    "BLOWDOWN_HEAVY": "BLOWDOWN_LIGHT",
    "BLOWDOWN_LIGHT": "BLOWDOWN_HEAVY",
    "BLOWDOWN_SNOWLOAD": "BLOWDOWN_LIGHT",
    "SNOW_PATCH": "SNOW_CONTINUOUS",
    "SNOW_CONTINUOUS": "SNOW_PATCH",
    "SPRING_SILTED": "WATER_TASTE_POOR",
    "WATER_TASTE_POOR": "SPRING_SILTED",
    "WASHOUT_MAJOR": "TREAD_EROSION",
    "TREAD_EROSION": "WASHOUT_MAJOR",
    "TREAD_COLLAPSE": "TREAD_EROSION",
    "STEPS_UNDERMINED": "BOARDWALK_BROKEN",
    "CAMP_SITES_FULL": "CAMP_SITES_TRASHED",
    "CAMP_SITES_TRASHED": "CAMP_SITES_FULL",
    "SIGN_DAMAGED": "BLAZE_FADED",
    "BLAZE_FADED": "CAIRN_MISSING",
    "POSTHOLING": "SNOW_PATCH",
    "SNOW_BRIDGE_THIN": "SNOW_CONTINUOUS",
}

# Clauses that map to no tag at all. Deliberately avoid water, crowds, bugs, shade, snow,
# mud, rain and trail-structure language so they cannot imply a tag by accident. Phrased
# register-neutrally in the third person, so the patrol and crew registers read naturally.
DISTRACTORS = [
    "wildflowers are peaking in the upper meadow",
    "a marmot was sitting out on the boulder field",
    "views from the saddle were clear to the far range",
    "the register box at the summit has plenty of pages left",
    "a pair of ravens worked the ridge all afternoon",
    "the aspens are just starting to turn colour",
    "elk tracks run all through the upper basin",
    "the rock in the upper section is clean granite",
    "a black bear was visible at distance and moved off immediately",
    "the old cabin foundation is still visible from the trail",
    "huckleberries are coming on along the upper bench",
    "a grouse flushed from the timber near the bench",
    "the light on the north face at sunrise is worth an early start",
    "the ridge above the basin was quiet all day",
    "there is a good flat spot just past the talus for a break",
    "the interpretive plaque at the overlook has a nice range panorama",
    "swifts were working the cliff band below the notch",
    "the larches along the upper switchbacks are healthy",
]

REGISTERS = ["logbook", "trip_report", "ranger_patrol", "crew_report", "satellite"]

# Scenario mix. Suppression cases are what the override rule is measured on, so they get a
# deliberate share; empty sets are the case the legacy service never emits.
SCENARIO_WEIGHTS = {"empty": 0.15, "suppression": 0.20, "impassable_only": 0.05, "normal": 0.60}

# Legacy service error profile, tuned so evaluate_original_model lands near 0.6.
LEGACY_EMPTY_INVENTS_TAG = 0.70
LEGACY_MISSES_SUPPRESSION = 0.75
LEGACY_OVER_TAGS = 0.12
LEGACY_NEAR_MISS_SWAP = 0.05
LEGACY_INVENTS_CODE = 0.03
LEGACY_ADDS_FENCE = 0.04

INVENTED_CODES = [
    "TRAIL_DAMAGE",
    "WATER_ISSUE",
    "SNOW_PRESENT",
    "ACCESS_PROBLEM",
    "MAINTENANCE_NEEDED",
    "HAZARD",
]

# The prompt the legacy service actually ran. Deliberately vaguer than the job
# description: it never states the override, the empty-set case, or the discriminators.
# remove_system_prompt_from_traces strips it, since the job description owns the task.
LEGACY_SYSTEM_PROMPT = (
    "You are the trail condition tagging service. Read the field report and return the "
    "condition tags that apply as JSON. Use the standard tag vocabulary."
)

MONTH_NAMES = ["May", "June", "July", "August", "September", "October"]


def taxonomy_by_family():
    """Group codes by family, preserving taxonomy order within each family."""
    grouped = {family: [] for family in FAMILIES}
    for entry in TAXONOMY:
        grouped[entry["family"]].append(entry["code"])
    return grouped


def canonical_order(codes):
    """Sort codes into taxonomy order. Targets are written in this order so training
    targets are consistent, even though the judge compares sets."""
    order = {entry["code"]: index for index, entry in enumerate(TAXONOMY)}
    return sorted(set(codes), key=lambda code: order[code])


def apply_suppression(codes):
    """The override rule: if any IMPASSABLE tag applies, the answer is only the
    IMPASSABLE tags."""
    family_of = {entry["code"]: entry["family"] for entry in TAXONOMY}
    impassable = [code for code in codes if family_of[code] == "IMPASSABLE"]
    if impassable:
        return canonical_order(impassable)
    return canonical_order(codes)


def sample_scenario(rng):
    names = list(SCENARIO_WEIGHTS)
    weights = [SCENARIO_WEIGHTS[name] for name in names]
    return rng.choices(names, weights=weights, k=1)[0]


def sample_described_tags(rng, scenario):
    """Pick the tags the report will describe. The answer is derived from these by the
    suppression rule, so a suppression case describes more than it answers."""
    grouped = taxonomy_by_family()
    non_impassable = grouped["OBSTRUCTION"] + grouped["SEASONAL"] + grouped["COMFORT"]

    if scenario == "empty":
        return []
    if scenario == "impassable_only":
        return rng.sample(grouped["IMPASSABLE"], rng.choice([1, 1, 2]))
    if scenario == "suppression":
        described = rng.sample(grouped["IMPASSABLE"], rng.choice([1, 1, 2]))
        described += rng.sample(non_impassable, rng.choice([1, 2, 2, 3]))
        return described
    return rng.sample(non_impassable, rng.choice([1, 2, 2, 3, 3, 4]))


def phrase_for(rng, code):
    for entry in TAXONOMY:
        if entry["code"] == code:
            return rng.choice(entry["phrases"])
    raise KeyError(code)


def render_report(rng, described, register):
    """Write the report text. Every described tag contributes one clause; distractors pad
    it out so the model cannot assume every sentence carries a tag."""
    clauses = [phrase_for(rng, code) for code in described]
    clauses += rng.sample(DISTRACTORS, rng.choice([1, 2, 2, 3]))
    rng.shuffle(clauses)

    date = f"2026-{rng.choice(MONTH_NAMES)} {rng.randint(1, 28)}"
    miles = round(rng.uniform(1.8, 26.4), 1)

    if register == "logbook":
        body = "; ".join(clauses)
        return f"Logbook entry {date} ({miles} mi) -- {body}."
    if register == "trip_report":
        first = clauses[0][0].upper() + clauses[0][1:]
        rest = " ".join(clause[0].upper() + clause[1:] + "." for clause in clauses[1:])
        return (
            f"Trip report, {date}. We covered {miles} miles out and back. "
            f"{first}. {rest}".strip()
        )
    if register == "ranger_patrol":
        body = " ".join(f"Patrol observed {clause}." for clause in clauses)
        return f"PATROL NOTE {date} | segment length {miles} mi\n{body}"
    if register == "crew_report":
        body = " ".join(clause[0].upper() + clause[1:] + "." for clause in clauses)
        return (
            f"Crew report {date}. Walked {miles} mi of the segment assessing "
            f"conditions. {body}"
        )
    body = " / ".join(clauses)
    return f"inreach msg {date} {miles}mi: {body}"


def legacy_answer(rng, described, truth):
    """The legacy service's logged answer. It over-tags, misses the override, refuses the
    empty set, confuses near-miss pairs, and sometimes fences its output."""
    all_codes = [entry["code"] for entry in TAXONOMY]
    predicted = list(truth)

    if not truth:
        if rng.random() < LEGACY_EMPTY_INVENTS_TAG:
            predicted = [rng.choice(all_codes)]
    elif len(described) > len(truth):
        # A suppression case: the legacy service lists everything it noticed.
        if rng.random() < LEGACY_MISSES_SUPPRESSION:
            predicted = canonical_order(described)
    else:
        if rng.random() < LEGACY_OVER_TAGS:
            extra = [code for code in all_codes if code not in predicted]
            predicted = canonical_order(
                predicted + rng.sample(extra, rng.choice([1, 1, 2]))
            )
        elif rng.random() < LEGACY_NEAR_MISS_SWAP:
            swappable = [code for code in predicted if code in NEAR_MISSES]
            if swappable:
                target = rng.choice(swappable)
                predicted = canonical_order(
                    [NEAR_MISSES[target] if code == target else code for code in predicted]
                )
        elif rng.random() < LEGACY_INVENTS_CODE:
            predicted = canonical_order(predicted) + [rng.choice(INVENTED_CODES)]

    payload = json.dumps({"tags": predicted})
    if rng.random() < LEGACY_ADDS_FENCE:
        return f"```json\n{payload}\n```"
    return payload


def build_trace(rng):
    scenario = sample_scenario(rng)
    described = sample_described_tags(rng, scenario)
    truth = apply_suppression(described)
    register = rng.choice(REGISTERS)
    report = render_report(rng, described, register)
    return {
        "messages": [
            {"role": "system", "content": LEGACY_SYSTEM_PROMPT},
            {"role": "user", "content": report},
            {"role": "assistant", "content": legacy_answer(rng, described, truth)},
        ]
    }


def build_task_description():
    """Render the taxonomy and the rules into the prompt every model sees."""
    lines = [
        "You are a trail condition tagging service. You receive one free-text field "
        "report about a section of trail and you return the condition tags that apply, "
        "as JSON. Output only the JSON object: no prose, no explanation, no markdown "
        "code fences.",
        "",
        'The output object has exactly one key: {"tags": [<tag code>, ...]}. The list '
        "may be empty. List tags in the order the taxonomy below gives them.",
        "",
        "THE TAXONOMY. These are the only tag codes that exist. Use them verbatim; "
        "never invent a code, never paraphrase one, and never emit a code that is not "
        "listed here.",
    ]
    for family in FAMILIES:
        lines.append("")
        lines.append(f"{family}:")
        for entry in TAXONOMY:
            if entry["family"] == family:
                lines.append(f"  {entry['code']}: {entry['definition']}")

    lines += [
        "",
        "RULE 1 - Apply a tag only when the report describes the condition that tag's "
        "definition names. Several tags are close neighbours and are told apart only by "
        "their definitions above, so read them rather than matching on surface words: "
        "WATER_LOW is about sources being dry while WATER_CARRY_LONG is about how far "
        "apart sources are; RUNOFF_ON_TREAD is water on the trail with no structure at "
        "fault while DRAIN_BLOCKED is a failed structure; BLOWDOWN_HEAVY is climbed "
        "over while BLOWDOWN_LIGHT is stepped over; SPRING_SILTED is cloudy water while "
        "WATER_TASTE_POOR is clear water that tastes bad.",
        "",
        "RULE 2 - The override. If ANY tag from the IMPASSABLE family applies, the "
        "answer contains ONLY the IMPASSABLE tags. Every OBSTRUCTION, SEASONAL and "
        "COMFORT tag is dropped, even when the report describes those conditions "
        "clearly and at length. A blocked trail is reported as blocked and nothing else.",
        "",
        "RULE 3 - If no tag applies, return an empty list. A report of a trail in good "
        'condition is {"tags": []}. Never reach for the closest tag to avoid returning '
        "nothing.",
        "",
        "RULE 4 - Every report carries a date and a mileage figure. Neither ever "
        "affects the tags. Ignore them.",
        "",
        "Example.",
        "Input: PATROL NOTE 2026-July 19 | segment length 8.4 mi",
        "Patrol observed mosquitoes were brutal the entire way. Patrol observed the "
        "footbridge at the lower crossing is gone entirely. Patrol observed the "
        "trailhead lot was full early.",
        'Output: {"tags": ["BRIDGE_OUT"]}',
        "(BRIDGE_OUT is IMPASSABLE, so Rule 2 fires: BUG_PRESSURE and PARKING_FULL are "
        "dropped even though the report states both.)",
    ]
    return "\n".join(lines)


JUDGE_INSTRUCTIONS = (
    "The prediction is good (1) only if it is a single valid JSON object with one key "
    '"tags" whose value is the SAME SET of tag codes as the reference. Compare as sets: '
    "ignore the order of the tags, ignore whitespace and indentation, and ignore "
    "duplicate entries. Every code in the reference must be present and no code outside "
    "the reference may be present, so a prediction that adds a plausible extra tag is "
    "bad, and so is one that omits a tag. An empty list in the prediction is good only "
    "if the reference is also empty. Mark the prediction bad (0) if it contains anything "
    "besides the JSON object, such as explanatory prose or markdown code fences, if it "
    "uses a tag code that does not appear in the reference, or if it is not valid JSON. "
    "Do not re-derive the correct answer yourself and do not reward reasoning that looks "
    "sound: judge only whether the tag set matches the reference."
)

GENERATION_INSTRUCTIONS = (
    "Each input is one free-text trail condition field report, and nothing else. Reports "
    "arrive in five registers, in roughly equal proportion: a terse trailhead logbook "
    "entry; a chatty first-person trip report of several sentences; a formal ranger "
    "patrol note; a trail crew work report; and a clipped satellite messenger message. "
    "Every report carries a date and a mileage figure, and both are decorative: vary "
    "them freely and never let them affect the tags.\n\n"
    "A report describes between zero and four taggable conditions, and always also "
    "contains one to three sentences of incidental detail that maps to no tag at all -- "
    "wildlife, views, flowers, light, timing, camp chat. Describe conditions in the "
    "reporter's own natural words rather than restating a tag's definition, and never "
    "name a tag code inside the report text.\n\n"
    "Across the dataset, cover the whole taxonomy: every family appears often, and the "
    "close-neighbour tags appear as distinct cases so the discriminator matters "
    "(sources dry versus sources far apart, water on tread versus a clogged structure, "
    "blowdown climbed over versus stepped over, cloudy water versus bad-tasting water). "
    "A substantial share of reports describe an IMPASSABLE condition alongside several "
    "other conditions, so the override rule is exercised, and a substantial share "
    "describe a trail in good order so the answer is an empty tag list."
)


def main(count: int, seed: int, output_dir: str):
    rng = random.Random(seed)
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    traces = [build_trace(rng) for _ in range(count)]
    traces_path = directory / "traces.jsonl"
    with traces_path.open("w") as handle:
        for trace in traces:
            handle.write(json.dumps(trace) + "\n")

    job_description = {
        "task_description": build_task_description(),
        "synthetic_data_generation_instructions": GENERATION_INSTRUCTIONS,
        "llm_as_a_judge_instructions": JUDGE_INSTRUCTIONS,
        "trace_processing_instructions": (
            "These are field reports logged by a legacy tagging service whose answers "
            "are often wrong. Rewrite the answer to the correct tag set for the report "
            "as written, applying the override and empty-list rules strictly. Never "
            "edit the report text itself: the reporter's wording, register, date and "
            "mileage stay exactly as they are.\n\n"
            "The assistant message content is itself a JSON object and must be emitted "
            'as a compact single-line JSON string of exactly the form {"tags": [...]}, '
            "with no surrounding prose, no markdown code fence, and no trailing "
            "commentary. When that object is carried inside a larger JSON structure, "
            "escape its quotes correctly so the outer structure stays valid JSON. Emit "
            "no reasoning or explanation anywhere in the rewritten conversation. The "
            "content must never be empty: a report with no applicable tags is the "
            'non-empty string {"tags": []}.\n\n'
            "Check the override before writing the answer. Work out every tag the report "
            "supports, then ask whether any of them is in the IMPASSABLE family; if one "
            "is, delete every OBSTRUCTION, SEASONAL and COMFORT tag from the answer and "
            "keep only the IMPASSABLE ones. Legacy answers frequently get this wrong by "
            "keeping the other conditions, and copying that mistake is the single most "
            "damaging error you can make here."
        ),
    }
    (directory / "job_description.json").write_text(
        json.dumps(job_description, indent=2) + "\n"
    )

    print(f"wrote {len(traces)} traces to {traces_path}")
    print(f"wrote job description to {directory / 'job_description.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument("--output-dir", default="traces-input")
    args = parser.parse_args()
    main(count=args.count, seed=args.seed, output_dir=args.output_dir)
