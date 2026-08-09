import random
import math
import io
import contextlib
import plotly.express as px
import pandas as pd
import numpy as np
import streamlit as st

# --- PAGE SETUP ---
st.set_page_config(page_title="Pokémon Sleep Simulation Dashboard", layout="wide")

# --- POKEMON BASE STATS & SPRITES ---
POKEMON_DATA = {
    "Wigglytuff": {"BASE_FREQ_MINS": 2750 / 60, "BASE_SKILL_RATE": 0.04,  "BASE_ING_RATE": 0.191, "BASE_INVENTORY": 32},
    "Sylveon":    {"BASE_FREQ_MINS": 2600 / 60, "BASE_SKILL_RATE": 0.04,  "BASE_ING_RATE": 0.178, "BASE_INVENTORY": 20},
    "Shuckle":    {"BASE_FREQ_MINS": 3600 / 60, "BASE_SKILL_RATE": 0.059, "BASE_ING_RATE": 0.205, "BASE_INVENTORY": 16},
    "Pawmot":     {"BASE_FREQ_MINS": 2400 / 60, "BASE_SKILL_RATE": 0.039, "BASE_ING_RATE": 0.141, "BASE_INVENTORY": 28},
    "Torterra":   {"BASE_FREQ_MINS": 2900 / 60, "BASE_SKILL_RATE": 0.048, "BASE_ING_RATE": 0.156, "BASE_INVENTORY": 27},
    "Gardevoir":  {"BASE_FREQ_MINS": 2400 / 60, "BASE_SKILL_RATE": 0.042, "BASE_ING_RATE": 0.144, "BASE_INVENTORY": 28}
}

POKEMON_SPRITES = {
    "Wigglytuff": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/40.png",
    "Sylveon":    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/700.png",
    "Shuckle":    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/213.png",
    "Pawmot":     "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/923.png",
    "Torterra":   "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/389.png",
    "Gardevoir":  "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/282.png"
}

# --- SIMULATOR CLASS ---
class PokemonSleepSimulator:
    MAX_ENERGY = 150
    SLEEP_CAP = 100
    E4E_HEAL_AMOUNT = 18

    def __init__(self, pokemon_name, level, subskills, nature, awake_hours=15.5,
                 sleep_hours=8.5, extra_inv=0):
        self.pokemon_name = pokemon_name
        self.level = level
        self.subskills = subskills
        self.nature = nature

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

    def simulate_day(self, start_energy, start_pity):
        energy = start_energy
        help_progress = 0.0
        inventory = 0
        hit_cap_minute = np.inf

        awake_helps = 0
        sleep_helps = 0
        awake_skill_triggers = 0
        banked_skills = 0
        pity_counter = start_pity

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

        return {
            "end_energy": energy,
            "awake_helps": awake_helps,
            "sleep_helps": sleep_helps,
            "awake_skill_triggers": awake_skill_triggers,
            "banked_skills": banked_skills,
            "hit_cap_minute": hit_cap_minute,
            "end_pity": pity_counter
        }

    def run(self, days=1000):
        print(f"--- SIMULATION SETTINGS ({days} Days) ---")
        print(f"Pokemon: {self.pokemon_name} | Level: {self.level}")
        print(f"Subskills: {self.subskills} | Nature: {self.nature}")
        print(f"Energy Nature Multiplier: {self.nature_energy}x")
        print(f"Berry Drop: {self.berry_count} (BFS: {'Yes' if 'BFS' in self.subskills else 'No'})")
        print(f"Calculated Freq: {self.final_freq:.2f} mins")
        print(f"Calculated Skill Rate: {self.skill_rate*100:.2f}%")
        print(f"Pity Threshold: {self.pity_threshold} helps")
        print(f"Max Inventory: {self.max_inv}")

        current_energy = 100
        current_pity = 0
        daily_results = []

        for day in range(1, days + 1):
            result = self.simulate_day(current_energy, current_pity)
            current_pity = result["end_pity"]

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
                "hit_cap_minute": result["hit_cap_minute"]
            })

            sleep_heal = min(100, 100 * self.nature_energy)
            morning_energy = min(self.SLEEP_CAP, result["end_energy"] + sleep_heal)
            current_energy = min(self.MAX_ENERGY, morning_energy + (result["banked_skills"] * self.effective_skill_heal))

        hit_cap_times = [result["hit_cap_minute"] for result in daily_results if result["hit_cap_minute"] != np.inf]
        
        if hit_cap_times:
            med_time = np.median(hit_cap_times) * 60
            hours, remainder = divmod(med_time, 3600)
            minutes, seconds = divmod(remainder, 60)
            print(f"Median Max Inventory Time: {int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}")
        else:
            print("Median Max Inventory Time: --:--:--")

        daily_banked_skills = np.array([result["banked_skills"] for result in daily_results])
        values, counts = np.unique(daily_banked_skills, return_counts=True)
        total_days = counts.sum()
        banked_dict = dict(zip(values, counts))

        print("--- Banked Skills Distribution ---")
        for i in range(3):
            count = banked_dict.get(i, 0)
            pct = (count / total_days) * 100
            print(f"{i} Banked Skills: {pct:>5.2f}%")
        print("-" * 35 + "\n")

        return pd.DataFrame(daily_results)

# --- STANDALONE PLOTLY RENDER FUNCTION ---
def render_plotly_charts(run_id, df):
    """Generates an interactive Plotly dashboard for the simulation metrics natively in Streamlit."""
    
    # Row 1: Total Triggers & Awake Efficiency
    col1, col2 = st.columns(2)
    
    with col1:
        data = df["total_triggers"].dropna()
        if not data.empty:
            counts = data.value_counts().sort_index().reset_index()
            counts.columns = ["Triggers", "Frequency"]
            
            fig1 = px.bar(counts, x="Triggers", y="Frequency", title="Total Triggers", 
                          color_discrete_sequence=["#87CEEB"])
            
            mean_val = data.mean()
            fig1.add_vline(x=mean_val, line_dash="dash", line_color="red", 
                           annotation_text=f"Mean: {mean_val:.2f}", annotation_position="top right")
            
            fig1.update_layout(xaxis=dict(dtick=1)) # Force integers on x-axis
            st.plotly_chart(fig1, use_container_width=True, key=f"bar_{run_id}")

    with col2:
        data = df["awake_efficiency"].dropna()
        if not data.empty:
            fig2 = px.histogram(df, x="awake_efficiency", title="Awake Efficiency", 
                                color_discrete_sequence=["#FA8072"], marginal="box", nbins=15)
            st.plotly_chart(fig2,  key=f"hist_awake_{run_id}")

    # Row 2: Sleep Efficiency & Daily Efficiency
    col3, col4 = st.columns(2)

    with col3:
        data = df["sleep_efficiency"].dropna()
        if not data.empty:
            fig3 = px.histogram(df, x="sleep_efficiency", title="Sleep Efficiency", 
                                color_discrete_sequence=["#3CB371"], marginal="box", nbins=15)
            st.plotly_chart(fig3, key=f"hist_sleep_{run_id}")

    with col4:
        data = df["daily_efficiency"].dropna()
        if not data.empty:
            fig4 = px.histogram(df, x="daily_efficiency", title="Daily Efficiency", 
                                color_discrete_sequence=["#800080"], marginal="box", nbins=15)
            st.plotly_chart(fig4, key=f"hist_daily_{run_id}")

# --- 1. INITIALIZE SESSION STATE ---
# Store summary stats for the data table
if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=[
        "ID", "Pokémon", "Mean Triggers", "Awake Eff", "Sleep Eff", "Daily Eff",
        "_level", "_subskills", "_nature_up", "_nature_down"
    ])
# Dictionary mapping Run ID to its full raw DataFrame and logs
if "history_data" not in st.session_state:
    st.session_state.history_data = {}

if "run_count" not in st.session_state: st.session_state.run_count = 0
if "ui_pokemon" not in st.session_state: st.session_state.ui_pokemon = "Wigglytuff"
if "ui_level" not in st.session_state: st.session_state.ui_level = 50
if "ui_subskills" not in st.session_state: st.session_state.ui_subskills = []
if "ui_nature_up" not in st.session_state: st.session_state.ui_nature_up = None
if "ui_nature_down" not in st.session_state: st.session_state.ui_nature_down = None


# --- 2. CALLBACK FUNCTIONS ---
def load_configuration(row):
    st.session_state.ui_pokemon = row["Pokémon"]
    st.session_state.ui_level = row["_level"]
    st.session_state.ui_subskills = row["_subskills"]
    st.session_state.ui_nature_up = row["_nature_up"]
    st.session_state.ui_nature_down = row["_nature_down"]

def delete_run(index, run_id):
    st.session_state.history = st.session_state.history.drop(index).reset_index(drop=True)
    if run_id in st.session_state.history_data:
        del st.session_state.history_data[run_id]


# --- 3. SIDEBAR INPUTS ---
st.sidebar.title("Simulation Settings")

st.sidebar.markdown("### Pokémon")
pokemon_name = st.sidebar.pills(
    "Select Pokémon",
    options=["Wigglytuff", "Sylveon", "Shuckle", "Pawmot", "Torterra", "Gardevoir"],
    selection_mode="single",
    key="ui_pokemon",
    label_visibility="collapsed"
)

if not pokemon_name: pokemon_name = "Wigglytuff"

col_sprite, col_level = st.sidebar.columns([1, 2], vertical_alignment="center")
with col_sprite: st.image(POKEMON_SPRITES[pokemon_name])
with col_level: level = st.number_input("Level", min_value=1, max_value=100, key="ui_level")

st.sidebar.divider()

st.sidebar.markdown("### Subskills")
subskills = st.sidebar.pills(
    "Click to toggle subskills",
    options=["STM", "STS", "HSM", "HSS", "HB", "IUL", "IUM", "IUS", "BFS"],
    selection_mode="multi",
    key="ui_subskills",
    label_visibility="collapsed"
)

st.sidebar.markdown("### Nature")
nature_up = st.sidebar.pills("Positive (+)", options=["MSC", "SOH", "ING", "ENG"], selection_mode="single", key="ui_nature_up")
nature_down = st.sidebar.pills("Negative (-)", options=["MSC", "SOH", "ING", "ENG"], selection_mode="single", key="ui_nature_down")

st.sidebar.divider()
col1, col2 = st.sidebar.columns([3,1], vertical_alignment="bottom")

days = col1.number_input("Simulation Days", min_value=10, max_value=1000, value=1000)

if col2.button("Run", type="primary", use_container_width=True):
    nature_list = []
    if nature_up: nature_list.append(f"{nature_up}+")
    if nature_down: nature_list.append(f"{nature_down}-")

    sim = PokemonSleepSimulator(pokemon_name, level, subskills, nature_list)

    # Capture console prints from sim.run()
    stdout_buffer = io.StringIO()
    with contextlib.redirect_stdout(stdout_buffer):
        df = sim.run(days=days)
    simulation_logs = stdout_buffer.getvalue()

    # Increment ID
    st.session_state.run_count += 1
    new_id = st.session_state.run_count
    
    # Store Raw DF & Logs in history_data dict mapped by ID
    st.session_state.history_data[new_id] = {
        "df": df,
        "logs": simulation_logs,
        "pokemon": pokemon_name
    }

    # Store Summary in history Dataframe
    new_run = {
        "ID": new_id,
        "Pokémon": pokemon_name,
        "Mean Triggers": round(df["total_triggers"].mean(), 2),
        "Awake Eff": round(df["awake_efficiency"].mean(), 2),
        "Sleep Eff": round(df["sleep_efficiency"].mean(), 2),
        "Daily Eff": round(df["daily_efficiency"].mean(), 2),
        "_level": level,
        "_subskills": subskills,
        "_nature_up": nature_up,
        "_nature_down": nature_down
    }

    new_row = pd.DataFrame([new_run])
    st.session_state.history = pd.concat([st.session_state.history, new_row], ignore_index=True)


# --- 4. MAIN DASHBOARD ---
st.title("Pokémon Sleep Simulation Dashboard")
st.markdown("💡 **Tip:** Click any row in the history table below to view its charts, load its configuration, or delete it.")

st.subheader("📋 Simulation History & Comparison Log")

if not st.session_state.history.empty:
    # Display the interactive dataframe
    event = st.dataframe(
        st.session_state.history,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "_level": None,
            "_subskills": None,
            "_nature_up": None,
            "_nature_down": None,
            "Mean Triggers": st.column_config.NumberColumn(format="%.2f"),
            "Awake Eff": st.column_config.NumberColumn(format="%.2f"),
            "Sleep Eff": st.column_config.NumberColumn(format="%.2f"),
            "Daily Eff": st.column_config.NumberColumn(format="%.2f"),
        }
    )

    # Determine which run to show details/plots for
    active_row_idx = None
    if len(event.selection.rows) > 0:
        active_row_idx = event.selection.rows[0]
    
    # If a row is selected in the UI, grab that row. Otherwise, just use the latest row (the bottom one) to show its charts
    active_row = st.session_state.history.iloc[active_row_idx] if active_row_idx is not None else st.session_state.history.iloc[-1]
    active_id = active_row["ID"]

    # If the user actually clicked the row, show them the config action buttons
    if active_row_idx is not None:
        with st.container(border=True):
            up_text = f"{active_row['_nature_up']}+" if active_row['_nature_up'] else "None"
            down_text = f"{active_row['_nature_down']}-" if active_row['_nature_down'] else "None"
            sub_text = ', '.join(active_row['_subskills']) if active_row['_subskills'] else 'None'


            st.markdown(f"""
            **Pokemon:** {pokemon_name} | **Level:** {active_row['_level']} | **Nature:** {up_text} / {down_text} | **Subskills:** {sub_text}
            """)

            col1, col2 = st.columns([1, 1])
            with col1:
                st.button("🔄 Load Configuration", on_click=load_configuration, args=(active_row,))
            with col2:
                st.button("🗑️ Delete Configuration", type="primary", on_click=delete_run, args=(active_row_idx, active_id))

    # --- 5. DYNAMIC PLOTTING & DETAILS AREA ---
    st.divider()
    st.subheader(f"📊 Details for Run #{active_id} ({active_row['Pokémon']})")
    
    # Fetch the dynamically saved DataFrame & logs
    if active_id in st.session_state.history_data:
        run_data = st.session_state.history_data[active_id]

        # 1. Show the Console logs
        with st.expander("📜 Console Logs", expanded=True):
            st.text(run_data["logs"])
            
        # 2. Render the Plotly charts cleanly in the Streamlit columns
        render_plotly_charts(active_id, run_data["df"])
        

else:
    st.info("No simulations run yet. Use the sidebar settings and click 'Run Simulation' to start!")