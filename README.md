# 💤 Pokémon Sleep Simulator & Analytics Dashboard

A fully interactive web application built with **Streamlit** and Python to simulate and analyze Pokémon performance in *Pokémon Sleep*. 

This tool models daily frequency, energy decay, skill triggers, inventory management, and efficiency metrics over customizable long-term periods.

---

## ✨ Features

- **Interactive Configuration Sidebar:**
  - Select your Pokémon using clickable visual pills with official sprites (`Wigglytuff`, `Sylveon`, `Shuckle`, `Pawmot`, `Torterra`, `Gardevoir`).
  - Set level, simulation duration (10–1000 days), toggle subskills (`STM`, `STS`, `BFS`, etc.), and pick Natures with enforced single positive/negative rules.
- **Simulation History Tracker:**
  - Automatically logs every run into an interactive history table.
  - Track metrics like Mean Triggers, Awake Efficiency, Sleep Efficiency, and Daily Efficiency.
  - Click any row in the history table to view its exact configuration details, **load it back into the sidebar**, or delete it.
- **Console Logs & Visualizations:**
  - Captures terminal prints and displays them inside a clean, collapsible console log expander.
  - Dynamically renders Matplotlib histogram distributions complete with 95% confidence intervals, IQR ranges, and mean performance lines.