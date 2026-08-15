"""
Pokémon Sleep simulation engine.
"""

import math
import random

import numpy as np
import pandas as pd

# --- POKEMON BASE STATS & SPRITES -------------------------------------------------

POKEMON_DATA = {
    "Wigglytuff": {"BASE_FREQ_MINS": 2750 / 60, "BASE_SKILL_RATE": 0.04,  "BASE_ING_RATE": 0.191, "BASE_INVENTORY": 32},
    "Sylveon":    {"BASE_FREQ_MINS": 2600 / 60, "BASE_SKILL_RATE": 0.04,  "BASE_ING_RATE": 0.178, "BASE_INVENTORY": 20},
    "Shuckle":    {"BASE_FREQ_MINS": 3600 / 60, "BASE_SKILL_RATE": 0.059, "BASE_ING_RATE": 0.205, "BASE_INVENTORY": 16},
    "Pawmot":     {"BASE_FREQ_MINS": 2400 / 60, "BASE_SKILL_RATE": 0.039, "BASE_ING_RATE": 0.141, "BASE_INVENTORY": 28},
    "Torterra":   {"BASE_FREQ_MINS": 2900 / 60, "BASE_SKILL_RATE": 0.048, "BASE_ING_RATE": 0.156, "BASE_INVENTORY": 27},
    "Gardevoir":  {"BASE_FREQ_MINS": 2400 / 60, "BASE_SKILL_RATE": 0.042, "BASE_ING_RATE": 0.144, "BASE_INVENTORY": 28},
}

POKEMON_SPRITES = {
    "Wigglytuff": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/40.png",
    "Sylveon":    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/700.png",
    "Shuckle":    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/213.png",
    "Pawmot":     "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/923.png",
    "Torterra":   "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/389.png",
    "Gardevoir":  "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/282.png",
}

# Sleep-ribbon "total sleep hours" milestones -> bonus max-inventory slots.
# Shown to the user as a ribbon/slider in the UI; translated internally to extra_inv.
RIBBON_TO_EXTRA_INV = {0: 0, 200: 1, 500: 3, 1000: 6, 2000: 8}

# Friendly axis / column labels reused by the UI layer for chart titles.
METRIC_LABELS = {
    "day": "Day",
    "start_energy": "Starting Energy",
    "end_energy": "Ending Energy",
    "awake_helps": "Awake Helps",
    "sleep_helps": "Sleep Helps",
    "daily_helps": "Total Helps (Day)",
    "awake_skill_triggers": "Awake Main Skill Triggers",
    "banked_skills": "Banked (Sleep) Skill Triggers",
    "total_triggers": "Total Skill Triggers",
    "awake_efficiency": "Awake Efficiency",
    "sleep_efficiency": "Sleep Efficiency",
    "daily_efficiency": "Daily Efficiency",
    "hit_cap_minute": "Minutes Until Inventory Cap (Sleep)",
}


class PokemonSleepSimulator:
    """Monte-Carlo simulator for a single Pokémon's daily help/skill/ingredient cycle."""

    MAX_ENERGY = 150
    SLEEP_CAP = 100
    E4E_HEAL_AMOUNT = 18

    def __init__(self, pokemon_name, level, subskills, nature, extra_hb=0,
                 awake_hours=15.5, sleep_hours=8.5, extra_inv=0):
        """
        Args:
            pokemon_name: key into POKEMON_DATA.
            level: Pokémon level (1-100).
            subskills: list of subskill codes, e.g. ["STM", "HB", "IUL"].
            nature: list of nature codes, e.g. ["MSC+", "SOH-"].
            extra_hb: number of teammates (0-4) providing the Helping Bonus subskill,
                each contributing +5% speed (renamed from the old `team_hb`).
            awake_hours: hours spent awake per simulated day.
            sleep_hours: hours spent asleep per simulated day.
            extra_inv: bonus max-inventory slots (e.g. from the sleep ribbon).
        """
        self.pokemon_name = pokemon_name
        self.level = level
        self.subskills = subskills
        self.nature = nature
        self.extra_hb = extra_hb

        self.awake_mins = round(awake_hours * 60)
        self.sleep_mins = round(sleep_hours * 60)
        self.total_mins = self.awake_mins + self.sleep_mins

        if pokemon_name not in POKEMON_DATA:
            raise ValueError(f"Pokemon '{pokemon_name}' not found in POKEMON_DATA.")

        self.base_data = POKEMON_DATA[pokemon_name]

        self.final_freq = 0.0
        self.skill_rate = 0.0
        self.ing_rate = 0.0
        self.max_inv = 0
        self.extra_inv = extra_inv
        self.ing_pool = []
        self.pity_threshold = 0
        self.nature_energy = 1.0
        self.berry_count = 1
        self.effective_skill_heal = 0

        self._apply_stats()

    def _apply_stats(self):
        base_freq_mins = self.base_data["BASE_FREQ_MINS"]
        base_skill_rate = self.base_data["BASE_SKILL_RATE"]
        base_ing_rate = self.base_data["BASE_ING_RATE"]
        base_inventory = self.base_data["BASE_INVENTORY"]

        skill_bonus = 0.0
        speed_bonus = 0.0
        inv_bonus = 0

        nature_skill = 1.0
        nature_speed = 1.0
        nature_ing = 1.0
        self.nature_energy = 1.0

        if "STM" in self.subskills: skill_bonus += 0.36
        if "STS" in self.subskills: skill_bonus += 0.18
        if "HSM" in self.subskills: speed_bonus += 0.14
        if "HSS" in self.subskills: speed_bonus += 0.07
        if "HB" in self.subskills:  speed_bonus += 0.05
        if "IUL" in self.subskills: inv_bonus += 18
        if "IUM" in self.subskills: inv_bonus += 12
        if "IUS" in self.subskills: inv_bonus += 6
        if "BFS" in self.subskills: self.berry_count = 2

        speed_bonus += self.extra_hb * 0.05
        speed_bonus = min(0.35, speed_bonus)

        if "MSC+" in self.nature: nature_skill = 1.2
        if "MSC-" in self.nature: nature_skill = 0.8
        if "SOH+" in self.nature: nature_speed = 0.9
        if "SOH-" in self.nature: nature_speed = 1.075
        if "ING+" in self.nature: nature_ing = 1.2
        if "ING-" in self.nature: nature_ing = 0.8
        if "ENG+" in self.nature: self.nature_energy = 1.2
        if "ENG-" in self.nature: self.nature_energy = 0.8

        level_time_mult = 1.0 - ((self.level - 1) * 0.002)

        self.final_freq = base_freq_mins * level_time_mult * (1.0 - speed_bonus) * nature_speed
        self.skill_rate = base_skill_rate * (1.0 + skill_bonus) * nature_skill
        self.ing_rate = base_ing_rate * nature_ing
        self.max_inv = base_inventory + inv_bonus + self.extra_inv

        self.ing_pool = [1]
        if self.level >= 30: self.ing_pool.append(2)
        if self.level >= 60: self.ing_pool.append(4)

        base_freq_sec = base_freq_mins * 60
        self.pity_threshold = math.ceil(142000 / base_freq_sec)
        self.effective_skill_heal = round(self.E4E_HEAL_AMOUNT * self.nature_energy)

    @staticmethod
    def get_speed_multiplier(energy):
        if energy >= 81: return 0.45
        elif energy >= 61: return 0.52
        elif energy >= 41: return 0.62
        elif energy >= 21: return 0.71
        else: return 1.00

    def simulate_day(self, start_energy, start_pity, checkpoint_interval=10, record_trace=True):
        """
        Simulate a single awake+sleep cycle.

        Args:
            checkpoint_interval: minutes between energy snapshots recorded in
                `energy_trace` (default: every 10 minutes). The same interval is
                used for every simulated day so traces line up across days.
            record_trace: if False, skip building `energy_trace` entirely
                (returns None for it). Used to only track a random sample of
                days when `days` is large, to keep memory bounded.

        Returns:
            dict with keys:
                end_energy (float): energy remaining at the end of the day.
                awake_helps (int): number of helps performed while awake.
                sleep_helps (int): number of helps performed while asleep.
                awake_skill_triggers (int): main-skill triggers while awake.
                banked_skills (int): main-skill triggers banked while asleep (capped at 2).
                hit_cap_minute (float): minutes into the sleep phase when inventory hit
                    max capacity, or np.inf if it never did.
                end_pity (int): pity counter carried into the next day.
                energy_trace (list[float] | None): energy level sampled every
                    `checkpoint_interval` minutes (plus the final minute), or
                    None if `record_trace` was False.
                checkpoint_minutes (list[int] | None): the minute-of-day each
                    `energy_trace` value was sampled at (same across all days),
                    or None if `record_trace` was False.
        """
        energy = start_energy
        help_progress = 0.0
        inventory = 0
        hit_cap_minute = np.inf

        awake_helps = 0
        sleep_helps = 0
        awake_skill_triggers = 0
        banked_skills = 0
        pity_counter = start_pity

        energy_trace = [energy] if record_trace else None
        checkpoint_minutes = [0] if record_trace else None

        for minute in range(self.total_mins):
            is_awake = minute < self.awake_mins

            if minute == self.awake_mins:
                inventory = 0

            multiplier = self.get_speed_multiplier(energy)
            actual_freq = self.final_freq * multiplier
            help_progress += 1.0 / actual_freq

            if help_progress >= 1.0:
                help_progress -= 1.0

                if is_awake:
                    awake_helps += 1
                    pity_counter += 1

                    if pity_counter >= self.pity_threshold or random.random() < self.skill_rate:
                        pity_counter = 0
                        awake_skill_triggers += 1
                        energy = min(self.MAX_ENERGY, energy + self.effective_skill_heal)
                else:
                    sleep_helps += 1

                    if inventory < self.max_inv:
                        pity_counter += 1
                        if random.random() < self.ing_rate:
                            inventory += random.choice(self.ing_pool)
                        else:
                            inventory += self.berry_count

                        if pity_counter >= self.pity_threshold or random.random() < self.skill_rate:
                            pity_counter = 0
                            banked_skills = min(2, banked_skills + 1)
                    else:
                        hit_cap_minute = minute - self.awake_mins

            energy = max(0.0, energy - 0.1)

            if record_trace:
                is_last_minute = minute == self.total_mins - 1
                if (minute + 1) % checkpoint_interval == 0 or is_last_minute:
                    energy_trace.append(energy)
                    checkpoint_minutes.append(minute + 1)

        return {
            "end_energy": energy,
            "awake_helps": awake_helps,
            "sleep_helps": sleep_helps,
            "awake_skill_triggers": awake_skill_triggers,
            "banked_skills": banked_skills,
            "hit_cap_minute": hit_cap_minute,
            "end_pity": pity_counter,
            "energy_trace": energy_trace,
            "checkpoint_minutes": checkpoint_minutes,
        }

    def run(self, days=1000, max_traced_days=1000):
        """
        Run the simulation for multiple consecutive days.

        Args:
            days: number of days to simulate.
            max_traced_days: max number of days to build a detailed energy
                trace for (used for the energy percentile chart). If `days`
                exceeds this, a random subset of days is traced instead of
                every day, to keep memory bounded — daily summary stats
                (helps, triggers, efficiency, etc.) are still computed for
                every day regardless.

        Returns:
            tuple(df, log):
                df (pd.DataFrame): one row per day with columns matching
                    METRIC_LABELS plus "day".
                log (dict): structured summary replacing the old console prints:
                    - "settings": dict of human-readable config values.
                    - "median_cap_time": "HH:MM:SS" string, or None if inventory
                      never hit max capacity on any day.
                    - "banked_distribution": list of {"banked_skills": int, "pct": float}
                      for 0, 1, 2 banked skills.
                    - "awake_hours" / "total_hours": floats, for marking the
                      sleep-phase boundary on the energy chart.
                    - "energy_percentiles": list of dicts, one per checkpoint,
                      each with "hour" and "p5"/"p25"/"p50"/"p75"/"p95" energy
                      values across the traced days (for a percentile-band
                      energy-over-time chart).
                    - "energy_traced_days": how many days the energy percentiles
                      were actually computed from.
        """
        settings = {
            "Pokémon": self.pokemon_name,
            "Level": self.level,
            "Subskills": ", ".join(self.subskills) if self.subskills else "None",
            "Nature": ", ".join(self.nature) if self.nature else "None",
            "Extra HB": self.extra_hb,
            "Berry Drop": f"{self.berry_count} ({'BFS' if 'BFS' in self.subskills else 'No BFS'})",
            "Calculated Freq (mins)": f"{self.final_freq:.2f}",
            "Calculated Skill Rate": f"{self.skill_rate * 100:.2f}%",
            "Pity Threshold (helps)": self.pity_threshold,
            "Max Inventory": self.max_inv,
        }

        current_energy = 100
        current_pity = 0
        daily_results = []
        energy_traces = []
        checkpoint_minutes = None

        sample_size = min(days, max_traced_days)
        traced_days = set(random.sample(range(1, days + 1), sample_size))

        for day in range(1, days + 1):
            result = self.simulate_day(current_energy, current_pity, record_trace=(day in traced_days))
            current_pity = result["end_pity"]
            if result["energy_trace"] is not None:
                energy_traces.append(result["energy_trace"])
                if checkpoint_minutes is None:
                    checkpoint_minutes = result["checkpoint_minutes"]

            daily_helps = result["awake_helps"] + result["sleep_helps"]
            total_triggers = result["awake_skill_triggers"] + result["banked_skills"]

            awake_eff = result["awake_helps"] / (self.awake_mins / self.final_freq)
            sleep_eff = result["sleep_helps"] / (self.sleep_mins / self.final_freq)
            daily_eff = daily_helps / (self.total_mins / self.final_freq)

            daily_results.append({
                "day": day,
                "start_energy": current_energy,
                "end_energy": result["end_energy"],
                "awake_helps": result["awake_helps"],
                "sleep_helps": result["sleep_helps"],
                "daily_helps": daily_helps,
                "awake_skill_triggers": result["awake_skill_triggers"],
                "banked_skills": result["banked_skills"],
                "total_triggers": total_triggers,
                "awake_efficiency": awake_eff,
                "sleep_efficiency": sleep_eff,
                "daily_efficiency": daily_eff,
                "hit_cap_minute": result["hit_cap_minute"],
            })

            sleep_heal = min(100, 100 * self.nature_energy)
            morning_energy = min(self.SLEEP_CAP, result["end_energy"] + sleep_heal)
            current_energy = min(self.MAX_ENERGY, morning_energy + (result["banked_skills"] * self.effective_skill_heal))

        hit_cap_times = [r["hit_cap_minute"] for r in daily_results if r["hit_cap_minute"] != np.inf]

        median_cap_time = None
        if hit_cap_times:
            med_time = np.median(hit_cap_times) * 60
            hours, remainder = divmod(med_time, 3600)
            minutes, seconds = divmod(remainder, 60)
            median_cap_time = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

        daily_banked_skills = np.array([r["banked_skills"] for r in daily_results])
        values, counts = np.unique(daily_banked_skills, return_counts=True)
        total_days = counts.sum()
        banked_dict = dict(zip(values, counts))

        banked_distribution = []
        for i in range(3):
            count = banked_dict.get(i, 0)
            pct = (count / total_days) * 100
            banked_distribution.append({"banked_skills": i, "pct": pct})

        energy_matrix = np.array(energy_traces)  # shape: (days, num_checkpoints)
        percentile_marks = [5, 25, 50, 75, 95]
        percentile_values = np.percentile(energy_matrix, percentile_marks, axis=0)

        energy_percentiles = []
        for i, minute in enumerate(checkpoint_minutes):
            row = {"hour": minute / 60.0}
            for mark, values in zip(percentile_marks, percentile_values):
                row[f"p{mark}"] = values[i]
            energy_percentiles.append(row)

        log = {
            "settings": settings,
            "median_cap_time": median_cap_time,
            "banked_distribution": banked_distribution,
            "awake_hours": self.awake_mins / 60.0,
            "total_hours": self.total_mins / 60.0,
            "energy_percentiles": energy_percentiles,
            "energy_traced_days": len(energy_traces),
        }

        return pd.DataFrame(daily_results), log