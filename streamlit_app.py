"""
Pokémon Sleep Simulation Dashboard — Streamlit UI layer.
"""

import random
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from simulator import (
    METRIC_LABELS,
    POKEMON_DATA,
    POKEMON_SPRITES,
    RIBBON_TO_EXTRA_INV,
    PokemonSleepSimulator,
)

# --- PAGE SETUP ---------------------------------------------------------------
st.set_page_config(page_title="Pokémon Sleep Simulation Dashboard", layout="wide", page_icon="😴")

st.markdown(
    """
<style>
    .block-container { padding-top: 2rem; }
    h1 { font-weight: 800; }
    div[data-testid="stMetric"] {
        background: rgba(135, 206, 235, 0.08);
        border: 1px solid rgba(135, 206, 235, 0.25);
        border-radius: 10px;
        padding: 10px 14px;
    }
    div[data-testid="stExpander"] {
        border-radius: 10px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# --- CONSTANTS ----------------------------------------------------------------
SUBSKILL_OPTIONS = ["STM", "STS", "HSM", "HSS", "HB", "IUL", "IUM", "IUS", "BFS"]
NATURE_OPTIONS = ["MSC", "SOH", "ING", "ENG"]

HISTORY_COLUMNS = [
    "ID", "Pokémon", "Level", "Subskills", "Nature", "Extra HB",
    "Mean Triggers", "Awake Eff", "Sleep Eff", "Daily Eff",
    "_level", "_subskills", "_nature_up", "_nature_down", "_extra_hb", "_extra_inv",
]


# --- STANDALONE PLOTLY RENDER FUNCTIONS ----------------------------------------
def render_distribution_charts(run_id, df, log):
    """Total triggers, awake/sleep/daily efficiency, banked skills, inventory cap time."""

    col1, col2 = st.columns(2)

    with col1:
        data = df["total_triggers"].dropna()
        if not data.empty:
            counts = data.value_counts().sort_index().reset_index()
            counts.columns = ["Triggers", "Frequency"]

            fig = px.bar(
                counts,
                x="Triggers",
                y="Frequency",
                title="Total Skill Triggers per Day",
                color_discrete_sequence=["#87CEEB"],
            )
            mean_val = data.mean()
            fig.add_vline(
                x=mean_val,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Mean: {mean_val:.2f}",
                annotation_position="top right",
            )
            fig.update_layout(
                xaxis=dict(dtick=1, title="Total Skill Triggers"),
                yaxis=dict(title="Number of Days"),
            )
            st.plotly_chart(fig, key=f"bar_triggers_{run_id}")

    with col2:
        data = df["awake_efficiency"].dropna()
        if not data.empty:
            fig = px.histogram(
                df,
                x="awake_efficiency",
                title="Awake Efficiency",
                color_discrete_sequence=["#FA8072"],
                marginal="box",
                nbins=15,
            )
            fig.update_layout(
                xaxis=dict(title="Awake Efficiency"),
                yaxis=dict(title="Number of Days"),
            )
            st.plotly_chart(fig, key=f"hist_awake_{run_id}")

    col3, col4 = st.columns(2)

    with col3:
        data = df["sleep_efficiency"].dropna()
        if not data.empty:
            fig = px.histogram(
                df,
                x="sleep_efficiency",
                title="Sleep Efficiency",
                color_discrete_sequence=["#3CB371"],
                marginal="box",
                nbins=15,
            )
            fig.update_layout(
                xaxis=dict(title="Sleep Efficiency"),
                yaxis=dict(title="Number of Days"),
            )
            st.plotly_chart(fig, key=f"hist_sleep_{run_id}")

    with col4:
        data = df["daily_efficiency"].dropna()
        if not data.empty:
            fig = px.histogram(
                df,
                x="daily_efficiency",
                title="Daily Efficiency",
                color_discrete_sequence=["#800080"],
                marginal="box",
                nbins=15,
            )
            fig.update_layout(
                xaxis=dict(title="Daily Efficiency"),
                yaxis=dict(title="Number of Days"),
            )
            st.plotly_chart(fig, key=f"hist_daily_{run_id}")

    # Row 3: Banked skills distribution + inventory cap time
    col5, col6 = st.columns(2)

    with col5:
        banked_df = pd.DataFrame(log.get("banked_distribution", []))
        if not banked_df.empty:
            fig = px.bar(
                banked_df,
                x="banked_skills",
                y="pct",
                title="Banked (Sleep) Skill Triggers Distribution",
                color_discrete_sequence=["#FFB347"],
            )
            fig.update_layout(
                xaxis=dict(dtick=1, title="Banked Skill Triggers per Day"),
                yaxis=dict(title="% of Days", ticksuffix="%"),
            )
            st.plotly_chart(fig, key=f"bar_banked_{run_id}")

    with col6:
        cap_data = df.loc[df["hit_cap_minute"] != float("inf"), "hit_cap_minute"]
        if cap_data.empty:
            st.markdown("**Time to Full Inventory (Sleep)**")
            st.info("Inventory never hit max capacity on any simulated day — nothing to plot.")
        else:
            cap_hours = cap_data / 60.0
            fig = px.histogram(
                cap_hours,
                title="Time to Full Inventory (Sleep)",
                color_discrete_sequence=["#9370DB"],
                marginal="box",
                nbins=15,
            )
            fig.update_layout(
                xaxis=dict(title="Hours into Sleep Phase Until Inventory Cap"),
                yaxis=dict(title="Number of Days"),
                showlegend=False,
            )
            st.plotly_chart(fig, key=f"hist_cap_{run_id}")


def render_settings_summary(log):
    """Render the run's settings/log dict as a clean Markdown block instead of raw console text."""
    settings = log.get("settings", {})
    lines = [f"**{key}:** {value}\n" for key, value in settings.items()]
    lines.append(
        f"**Median Time to Full Inventory:** "
        f"{log.get('median_cap_time') if log.get('median_cap_time') else '— (never hit cap)'}"
    )
    st.markdown("\n".join(lines))


def render_energy_percentile_chart(run_id, log):
    """Energy over the day as a percentile fan chart (5-95 band, 25-75 band, median line)."""
    energy_pct = pd.DataFrame(log.get("energy_percentiles", []))
    if energy_pct.empty:
        st.info("No energy trace data available for this run.")
        return

    hours = energy_pct["hour"]
    hours_band = pd.concat([hours, hours[::-1]])

    fig = go.Figure()

    # Outer band: 5th-95th percentile
    fig.add_trace(
        go.Scatter(
            x=hours_band,
            y=pd.concat([energy_pct["p95"], energy_pct["p5"][::-1]]),
            fill="toself",
            fillcolor="rgba(135,206,235,0.20)",
            line=dict(color="rgba(255,255,255,0)"),
            name="5th–95th percentile",
            hoverinfo="skip",
        )
    )

    # Inner band: 25th-75th percentile
    fig.add_trace(
        go.Scatter(
            x=hours_band,
            y=pd.concat([energy_pct["p75"], energy_pct["p25"][::-1]]),
            fill="toself",
            fillcolor="rgba(135,206,235,0.45)",
            line=dict(color="rgba(255,255,255,0)"),
            name="25th–75th percentile",
            hoverinfo="skip",
        )
    )

    # Median line
    fig.add_trace(
        go.Scatter(
            x=hours,
            y=energy_pct["p50"],
            mode="lines",
            line=dict(color="#1f77b4", width=2.5),
            name="Median Energy",
        )
    )

    fig.add_vline(
        x=log.get("awake_hours"),
        line_dash="dot",
        line_color="gray",
        annotation_text="Sleep starts",
        annotation_position="top",
    )

    # Transparent threshold bands with multiplier-only labels
    threshold_bands = [
        (81, 150, "2.22x", "rgba(255, 99, 132, 0.10)"),
        (61, 80,  "1.92x", "rgba(255, 159, 64, 0.10)"),
        (41, 60,  "1.61x", "rgba(255, 205, 86, 0.10)"),
        (21, 40,  "1.41x", "rgba(75, 192, 192, 0.10)"),
        (1,  20,  "1.25x", "rgba(54, 162, 235, 0.10)"),
    ]

    x_min = float(hours.min())
    x_max = float(hours.max())
    x_mid = (x_min + x_max) / 2

    for y0, y1, label, color in threshold_bands:
        # band
        fig.add_hrect(
            y0=y0, y1=y1,
            fillcolor=color,
            line_width=0,
            layer="below",
        )
        # centered label in band
        fig.add_annotation(
            x=x_mid,
            y=(y0 + y1) / 2,
            text=label,
            showarrow=False,
            font=dict(size=11, color="rgba(80,80,80,0.9)"),
        )

    fig.update_layout(
        xaxis=dict(title="Hours Elapsed", dtick=2),
        yaxis=dict(title="Energy"),
        legend_title_text="",
        legend=dict(
                    orientation="h",   # Make the legend horizontal
                    yanchor="top",     # Anchor the top of the legend box
                    y=-0.3,            # Push it below the x-axis (0 is the bottom of the chart)
                    xanchor="center",  # Anchor the middle of the legend box
                    x=0.5              # Center it horizontally
                )
    )
    st.plotly_chart(fig, key=f"energy_pct_{run_id}")


# --- HELPER FUNCTIONS -----------------------------------------------------------
def get_max_subskills(lvl: int) -> int:
    if lvl >= 80:
        return 5
    if lvl >= 70:
        return 4
    if lvl >= 50:
        return 3
    if lvl >= 25:
        return 2
    if lvl >= 10:
        return 1
    return 0


def build_nature_list(nature_up, nature_down):
    if nature_up and nature_down and nature_up == nature_down:
        return []

    nature_list = []
    if nature_up:
        nature_list.append(f"{nature_up}+")
    if nature_down:
        nature_list.append(f"{nature_down}-")
    return nature_list


def simulate_once(pokemon_name, level, subskills, nature_up, nature_down, days, extra_hb, ribbon_hours):
    nature_list = build_nature_list(nature_up, nature_down)
    extra_inv = RIBBON_TO_EXTRA_INV.get(ribbon_hours, 0)

    sim = PokemonSleepSimulator(
        pokemon_name,
        level,
        subskills,
        nature_list,
        extra_hb=extra_hb,
        extra_inv=extra_inv,
    )
    df, log = sim.run(days=days)
    return df, log


def append_run_result(
    pokemon_name,
    level,
    subskills,
    nature_up,
    nature_down,
    extra_hb,
    ribbon_hours,
    df,
    log,
):
    st.session_state.run_count += 1
    new_id = st.session_state.run_count

    st.session_state.history_data[new_id] = {"df": df, "log": log, "pokemon": pokemon_name}

    nature_list = build_nature_list(nature_up, nature_down)

    new_run = {
        "ID": new_id,
        "Pokémon": pokemon_name,
        "Level": level,
        "Subskills": ", ".join(subskills) if subskills else "None",
        "Nature": ", ".join(nature_list) if nature_list else "Neutral",
        "Extra HB": extra_hb,
        "Mean Triggers": round(df["total_triggers"].mean(), 2),
        "Awake Eff": round(df["awake_efficiency"].mean(), 2),
        "Sleep Eff": round(df["sleep_efficiency"].mean(), 2),
        "Daily Eff": round(df["daily_efficiency"].mean(), 2),
        "_level": level,
        "_subskills": subskills,
        "_nature_up": nature_up,
        "_nature_down": nature_down,
        "_extra_hb": extra_hb,
        "_extra_inv": ribbon_hours,
    }

    st.session_state.history = pd.concat(
        [st.session_state.history, pd.DataFrame([new_run])],
        ignore_index=True,
    )


def sample_subskills_for_level(level: int, allowed_pool: list[str]) -> list[str]:
    slots = get_max_subskills(level)
    if slots <= 0 or not allowed_pool:
        return []
    return random.sample(allowed_pool, k=min(slots, len(allowed_pool)))


def validate_random_inputs(level_min, level_max, subskill_pool):
    if level_min > level_max:
        return False, "Level min cannot be greater than level max."
    if level_max >= 10 and len(subskill_pool) == 0:
        return False, "Please select at least one subskill option (or keep max level below 10)."
    return True, ""


def run_randomized_batch(
    n_runs: int,
    pokemon_choice: str,
    level_min: int,
    level_max: int,
    allowed_subskills: list[str],
    allowed_nature_up: list[str],
    allowed_nature_down: list[str],
    days: int,
    extra_hb_fixed: int = 0,
    ribbon_hours_fixed: int = 0,
):
    progress = st.progress(0, text="Starting randomized runs...")
    status = st.empty()

    for i in range(n_runs):
        lvl = random.randint(level_min, level_max)
        subs = sample_subskills_for_level(lvl, allowed_subskills)

        up = random.choice(allowed_nature_up) if allowed_nature_up else None
        down = random.choice(allowed_nature_down) if allowed_nature_down else None

        df, log = simulate_once(
            pokemon_name=pokemon_choice,
            level=lvl,
            subskills=subs,
            nature_up=up,
            nature_down=down,
            days=days,
            extra_hb=extra_hb_fixed,
            ribbon_hours=ribbon_hours_fixed,
        )

        append_run_result(
            pokemon_name=pokemon_choice,
            level=lvl,
            subskills=subs,
            nature_up=up,
            nature_down=down,
            extra_hb=extra_hb_fixed,
            ribbon_hours=ribbon_hours_fixed,
            df=df,
            log=log,
        )

        nature_list = build_nature_list(up, down)
        nature_text = ", ".join(nature_list) if nature_list else "Neutral"
        subskills_text = ", ".join(subs) if subs else "None"

        # progress update
        pct = int(((i + 1) / n_runs) * 100)
        progress.progress(pct, text=f"Generating randomized runs... {i+1}/{n_runs}")
        status.write(
            f"Latest run: #{st.session_state.run_count} | "
            f"Pokémon: {pokemon_choice} | "
            f"Level: {lvl} | "
            f"Subskills: {subskills_text} | "
            f"Nature: {nature_text} | "
        )

    progress.progress(100, text="Done ✅")

def format_equation(coeffs):
    """coeffs: highest-degree-first, as returned by np.polyfit."""
    degree = len(coeffs) - 1
    terms = []
    for i, c in enumerate(coeffs):
        power = degree - i
        if power == 0:
            terms.append(f"{c:+.4g}")
        elif power == 1:
            terms.append(f"{c:+.4g}x")
        else:
            terms.append(f"{c:+.4g}x{'²' if power == 2 else f'^{power}'}")
    return "y = " + " ".join(terms).lstrip("+").strip()


# --- SESSION STATE --------------------------------------------------------------
if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=HISTORY_COLUMNS)
if "history_data" not in st.session_state:
    st.session_state.history_data = {}
if "run_count" not in st.session_state:
    st.session_state.run_count = 0

# Sidebar UI state
if "ui_pokemon" not in st.session_state:
    st.session_state.ui_pokemon = "Wigglytuff"
if "ui_level" not in st.session_state:
    st.session_state.ui_level = 50
if "ui_subskills" not in st.session_state:
    st.session_state.ui_subskills = []
if "ui_nature_up" not in st.session_state:
    st.session_state.ui_nature_up = None
if "ui_nature_down" not in st.session_state:
    st.session_state.ui_nature_down = None
if "ui_extra_hb" not in st.session_state:
    st.session_state.ui_extra_hb = 0
if "ui_ribbon" not in st.session_state:
    st.session_state.ui_ribbon = 0


# --- CALLBACKS -----------------------------------------------------------------
def load_configuration(row):
    st.session_state.ui_pokemon = row["Pokémon"]
    st.session_state.ui_level = row["_level"]
    st.session_state.ui_subskills = row["_subskills"]
    st.session_state.ui_nature_up = row["_nature_up"]
    st.session_state.ui_nature_down = row["_nature_down"]
    st.session_state.ui_extra_hb = row["_extra_hb"]
    st.session_state.ui_ribbon = row["_extra_inv"]


def delete_run(index, run_id):
    st.session_state.history = st.session_state.history.drop(index).reset_index(drop=True)
    if run_id in st.session_state.history_data:
        del st.session_state.history_data[run_id]


def enforce_max_subskills():
    selected = st.session_state.get("ui_subskills", [])
    current_level = st.session_state.get("ui_level", 1)
    allowed = get_max_subskills(current_level)
    if len(selected) > allowed:
        st.session_state.ui_subskills = selected[:allowed]
        st.toast(f"⚠️ Level {current_level} allows maximum {allowed} subskills!")

def reset_all_history():
    st.session_state.history = pd.DataFrame(columns=HISTORY_COLUMNS)
    st.session_state.history_data = {}
    st.session_state.run_count = 0

# --- SIDEBAR INPUTS -------------------------------------------------------------
st.sidebar.title("⚙️ Simulation Settings")

st.sidebar.markdown("### Pokémon")
pokemon_name = st.sidebar.pills(
    "Select Pokémon",
    options=list(POKEMON_DATA.keys()),
    selection_mode="single",
    key="ui_pokemon",
    label_visibility="collapsed",
)
if not pokemon_name:
    pokemon_name = "Wigglytuff"

col_sprite, col_level = st.sidebar.columns([1, 2], vertical_alignment="center")
with col_sprite:
    st.image(POKEMON_SPRITES[pokemon_name])
with col_level:
    level = st.number_input("Level", min_value=1, max_value=100, key="ui_level")

max_allowed = get_max_subskills(level)

if len(st.session_state.get("ui_subskills", [])) > max_allowed:
    st.session_state.ui_subskills = st.session_state.ui_subskills[:max_allowed]

st.sidebar.divider()
st.sidebar.markdown(f"### Subskills ({len(st.session_state.ui_subskills)}/{max_allowed} Unlocked)")

if max_allowed == 0:
    st.sidebar.info("🔒 Subskills unlock starting at Level 10.")
else:
    st.sidebar.pills(
        "Click to toggle subskills",
        options=SUBSKILL_OPTIONS,
        selection_mode="multi",
        key="ui_subskills",
        on_change=enforce_max_subskills,
        label_visibility="collapsed",
    )

# Always safe
subskills = st.session_state.get("ui_subskills", [])

col_label, col_input = st.sidebar.columns([1, 1], vertical_alignment="center")
with col_label:
    st.markdown("**Extra HB**", help="Each teammate with Helping Bonus adds +5% speed (max 4).")
with col_input:
    extra_hb = st.number_input(
        "Extra HB",
        min_value=0,
        max_value=4,
        key="ui_extra_hb",
        label_visibility="collapsed",
    )

st.sidebar.divider()
st.sidebar.markdown("### Nature")
nature_up = st.sidebar.pills(
    "Positive (+)",
    options=NATURE_OPTIONS,
    selection_mode="single",
    key="ui_nature_up",
)
nature_down = st.sidebar.pills(
    "Negative (-)",
    options=NATURE_OPTIONS,
    selection_mode="single",
    key="ui_nature_down",
)

st.sidebar.divider()
st.sidebar.markdown("### Sleep Ribbon")
ribbon_choice = st.sidebar.pills(
    "Total Sleep Hours Ribbon",
    options=list(RIBBON_TO_EXTRA_INV.keys()),
    format_func=lambda h: f"{h:,}h",
    selection_mode="single",
    key="ui_ribbon",
    help="Ribbon milestones grant bonus max-inventory slots: 0h→+0, 200h→+1, 500h→+3, 1000h→+6, 2000h→+8.",
)

st.sidebar.divider()
col1, col2 = st.sidebar.columns([3, 1], vertical_alignment="bottom")
days = col1.number_input("Simulation Days", min_value=10, max_value=10000, value=1000)

if col2.button("Run", type="primary"):
    df, log = simulate_once(
        pokemon_name=pokemon_name,
        level=level,
        subskills=subskills,
        nature_up=nature_up,
        nature_down=nature_down,
        days=days,
        extra_hb=extra_hb,
        ribbon_hours=ribbon_choice,
    )

    append_run_result(
        pokemon_name=pokemon_name,
        level=level,
        subskills=subskills,
        nature_up=nature_up,
        nature_down=nature_down,
        extra_hb=extra_hb,
        ribbon_hours=ribbon_choice,
        df=df,
        log=log,
    )


# --- MAIN DASHBOARD -------------------------------------------------------------
st.title("😴 Pokémon Sleep Simulation Dashboard")

with st.expander("🎲 Randomized Runs Generator", expanded=False):
    st.caption("Generate multiple randomized configurations in one click.")

    c1, c2 = st.columns([1, 2])
    with c1:
        rand_n_runs = st.number_input(
            "Number of randomized runs",
            min_value=1,
            max_value=50,
            value=20,
            step=1,
            key="rand_n_runs",
        )
        rand_pokemon = st.selectbox(
            "Pokémon",
            options=list(POKEMON_DATA.keys()),
            index=0,
            key="rand_pokemon",
        )
        rand_days = st.number_input(
            "Simulation days per run",
            min_value=10,
            max_value=10000,
            value=1000,
            step=10,
            key="rand_days",
        )

    with c2:
        lvl_col1, lvl_col2 = st.columns(2)
        with lvl_col1:
            rand_level_min = st.number_input(
                "Level min",
                min_value=1,
                max_value=st.session_state.get("rand_level_max", 100),  # cannot exceed max
                value=min(st.session_state.get("rand_level_min", 30), st.session_state.get("rand_level_max", 100)),
                step=1,
                key="rand_level_min",
            )

        with lvl_col2:
            rand_level_max = st.number_input(
                "Level max",
                min_value=st.session_state.get("rand_level_min", 1),    
                max_value=100,
                value=max(st.session_state.get("rand_level_max", 70), st.session_state.get("rand_level_min", 1)),
                step=1,
                key="rand_level_max",
            )

        rand_subskills_pool = st.multiselect(
            "Subskill options (random pool)",
            options=SUBSKILL_OPTIONS,
            default=SUBSKILL_OPTIONS,
            key="rand_subskills_pool",
            help="Each run samples unique subskills from this pool based on unlocked slots at that level.",
        )

        nat_col1, nat_col2 = st.columns(2)
        with nat_col1:
            rand_nature_up_pool = st.multiselect(
                "Nature (+) options",
                options=NATURE_OPTIONS,
                default=NATURE_OPTIONS,
                key="rand_nature_up_pool",
            )
        with nat_col2:
            rand_nature_down_pool = st.multiselect(
                "Nature (-) options",
                options=NATURE_OPTIONS,
                default=NATURE_OPTIONS,
                key="rand_nature_down_pool",
            )

        extra_col1, extra_col2 = st.columns(2)
        with extra_col1:
            rand_extra_hb = st.number_input(
                "Fixed Extra HB",
                min_value=0,
                max_value=4,
                value=0,
                step=1,
                key="rand_extra_hb",
            )
        with extra_col2:
            rand_ribbon = st.selectbox(
                "Fixed Sleep Ribbon (hours)",
                options=list(RIBBON_TO_EXTRA_INV.keys()),
                format_func=lambda h: f"{h:,}h",
                index=0,
                key="rand_ribbon",
            )

    if st.button("Generate Randomized Runs", type="primary", key="btn_generate_randomized_runs"):
        ok, msg = validate_random_inputs(rand_level_min, rand_level_max, rand_subskills_pool)
        if not ok:
            st.error(msg)
        else:
            run_randomized_batch(
                n_runs=int(rand_n_runs),
                pokemon_choice=rand_pokemon,
                level_min=int(rand_level_min),
                level_max=int(rand_level_max),
                allowed_subskills=rand_subskills_pool,
                allowed_nature_up=rand_nature_up_pool,
                allowed_nature_down=rand_nature_down_pool,
                days=int(rand_days),
                extra_hb_fixed=int(rand_extra_hb),
                ribbon_hours_fixed=int(rand_ribbon),
            )
            st.success(f"Generated {int(rand_n_runs)} randomized runs for {rand_pokemon}.")
            st.rerun()

top_left, top_right = st.columns([4, 1], vertical_alignment="bottom")
with top_left:
    st.subheader("📋 Simulation History & Comparison Log")
with top_right:
    if st.button("🧹 Reset History", type="secondary"):
        reset_all_history()
        st.success("All history cleared.")
        st.rerun()
st.caption("Click any row to view its charts, load its configuration, or delete it.")

if not st.session_state.history.empty:
    event = st.dataframe(
        st.session_state.history,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "ID": None,
            "_level": None,
            "_subskills": None,
            "_nature_up": None,
            "_nature_down": None,
            "_extra_hb": None,
            "_extra_inv": None,
            "Mean Triggers": st.column_config.NumberColumn(format="%.2f"),
            "Awake Eff": st.column_config.NumberColumn(format="%.2f"),
            "Sleep Eff": st.column_config.NumberColumn(format="%.2f"),
            "Daily Eff": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    active_row_idx = event.selection.rows[0] if len(event.selection.rows) > 0 else None
    active_row = (
        st.session_state.history.iloc[active_row_idx]
        if active_row_idx is not None
        else st.session_state.history.iloc[-1]
    )
    active_id = active_row["ID"]

    if active_row_idx is not None:
        with st.container(border=True):
            col1, col2 = st.columns([1, 1])
            with col1:
                st.button("🔄 Load Configuration", on_click=load_configuration, args=(active_row,))
            with col2:
                st.button(
                    "🗑️ Delete Configuration",
                    type="primary",
                    on_click=delete_run,
                    args=(active_row_idx, active_id),
                )

    st.divider()

    main_view = st.segmented_control(
        "View Mode",
        options=["📊 Details", "🔀 Compare Runs"],
        default="📊 Details",
        label_visibility="collapsed",
    )

    if main_view == "📊 Details":
        if active_id in st.session_state.history_data:
            run_data = st.session_state.history_data[active_id]
            st.subheader(f"Run #{active_id}")
            tab_overview, tab_charts, tab_energy = st.tabs(
                ["🧾 Pokemon Stats", "📈 Distributions", "🔋 Energy"]
            )

            with tab_overview:
                render_settings_summary(run_data["log"])
            with tab_charts:
                render_distribution_charts(active_id, run_data["df"], run_data["log"])
            with tab_energy:
                render_energy_percentile_chart(active_id, run_data["log"])

    elif main_view == "🔀 Compare Runs":
        st.subheader("Efficiency vs. Skill Triggers — All Saved Runs")
        st.markdown("Each point is one saved run, averaged across its simulated days. ")

        EFFICIENCY_METRICS = ["awake_efficiency", "sleep_efficiency", "daily_efficiency"]
        METRIC_COLORS = {
            "awake_efficiency": "#FA8072",
            "sleep_efficiency": "#3CB371",
            "daily_efficiency": "#800080",
        }
        
        fit_type = st.radio("Trend line fit", ["Linear", "Quadratic"], horizontal=True, key="fit_type")
        fit_degree = 1 if fit_type == "Linear" else 2

        run_points = []
        history_by_id = st.session_state.history.set_index("ID", drop=False)

        for rid, run_data_i in st.session_state.history_data.items():
            run_df = run_data_i["df"]
            if run_df.empty:
                continue

            run_label = f"#{rid} · {run_data_i['pokemon']}"
            mean_triggers = run_df["total_triggers"].mean()

            # metadata from saved history table (always present)
            if rid in history_by_id.index:
                row = history_by_id.loc[rid]
                level_val = row["Level"]
                subskills_val = row["Subskills"]
                nature_val = row["Nature"]
                extra_hb_val = row["Extra HB"]
            else:
                level_val = "N/A"
                subskills_val = "N/A"
                nature_val = "N/A"
                extra_hb_val = "N/A"

            for metric in EFFICIENCY_METRICS:
                run_points.append(
                    {
                        "Run": run_label,
                        "pokemon": run_data_i["pokemon"],
                        "level": level_val,
                        "subskills": subskills_val,
                        "nature": nature_val,
                        "extra_hb": extra_hb_val,
                        "total_triggers": run_df["total_triggers"].mean(),
                        "metric": metric,
                        "value": run_df[metric].mean(),
                    }
                )

        if not run_points:
            st.info("No runs available yet.")
        else:
            points_df = pd.DataFrame(run_points)
            fig = go.Figure()

            for metric in EFFICIENCY_METRICS:
                label = METRIC_LABELS.get(metric, metric)
                color = METRIC_COLORS.get(metric)
                metric_df = points_df[points_df["metric"] == metric]

                fig.add_trace(
                    go.Scatter(
                        x=metric_df["total_triggers"],
                        y=metric_df["value"],
                        mode="markers",
                        name=label,
                        marker=dict(size=10, color=color),
                        customdata=metric_df[["Run", "pokemon", "level", "subskills", "nature", "extra_hb"]].values,
                        hovertemplate=(
                            "<b>%{customdata[0]}</b><br>"
                            "Pokémon: %{customdata[1]}<br>"
                            "Level: %{customdata[2]}<br>"
                            "Subskills: %{customdata[3]}<br>"
                            "Nature: %{customdata[4]}<br>"
                            "Extra HB: %{customdata[5]}<br>"
                            "Triggers: %{x:.2f}<br>"
                            "Efficiency: %{y:.3f}"
                            "<extra></extra>"
                        ),
                    )
                )


                n_unique = metric_df["total_triggers"].nunique()
                if n_unique >= fit_degree + 1:
                    coeffs = np.polyfit(metric_df["total_triggers"], metric_df["value"], fit_degree)
                    x_fit = np.linspace(metric_df["total_triggers"].min(), metric_df["total_triggers"].max(), 50)
                    y_fit = np.polyval(coeffs, x_fit)

                    fig.add_trace(
                        go.Scatter(
                            x=x_fit,
                            y=y_fit,
                            mode="lines",
                            name=f"{label} trend",
                            line=dict(color=color, dash="dash"),
                            hoverinfo="skip",
                        )
                    )

                    fig.add_annotation(
                        x=x_fit[-1],
                        y=y_fit[-1],
                        text=format_equation(coeffs),
                        showarrow=False,
                        xanchor="left",
                        yshift=4,
                        font=dict(color=color, size=11),
                    )

            fig.update_layout(
                xaxis=dict(title=METRIC_LABELS.get("total_triggers", "Total Skill Triggers")),
                yaxis=dict(title="Efficiency"),
                legend_title_text="Metric (click to hide/show)",
                legend=dict(
                    orientation="h",   # Make the legend horizontal
                    yanchor="top",     # Anchor the top of the legend box
                    y=-0.3,            # Push it below the x-axis (0 is the bottom of the chart)
                    xanchor="center",  # Anchor the middle of the legend box
                    x=0.5              # Center it horizontally
                )
            )
            st.plotly_chart(fig, key="compare_efficiency_vs_triggers")
else:
    st.info("No simulations run yet. Use the sidebar settings and click 'Run' to start!")