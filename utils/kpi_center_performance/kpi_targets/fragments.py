# utils/kpi_center_performance/kpi_targets/fragments.py
"""
Streamlit Fragments for KPI Center Performance - KPI & Targets Tab.

Contains:
- kpi_assignments_fragment: KPI assignments with hierarchy rollup
- kpi_progress_fragment: KPI progress with per-center breakdown
- kpi_center_ranking_fragment: KPI Center performance ranking
"""

import logging
from typing import Dict, Optional
import pandas as pd
import streamlit as st

from ..common.fragments import format_currency, get_rank_display

logger = logging.getLogger(__name__)


# =============================================================================
# ICON CONSTANTS - Synced with kpi_center_selector.py
# =============================================================================
ICON_ROOT = "🏢"      # Root/Company level (level 0)
ICON_REGION = "🌏"    # Region level (level 1)
ICON_BRANCH = "📍"    # Branch/Leaf level
ICON_FOLDER = "📁"    # Has children (non-leaf)


def get_kpi_center_icon(level: int, is_leaf: bool) -> str:
    """
    Get appropriate icon for KPI Center based on level and leaf status.
    Synced with kpi_center_selector.py for consistency.
    
    Args:
        level: Hierarchy level (0=root, 1=region, 2+=branch)
        is_leaf: Whether this is a leaf node (no children)
        
    Returns:
        Emoji icon string
    """
    if level == 0:
        return ICON_ROOT if not is_leaf else ICON_BRANCH
    elif level == 1:
        return ICON_REGION if not is_leaf else ICON_BRANCH
    else:
        return ICON_FOLDER if not is_leaf else ICON_BRANCH


def build_hierarchy_groups(
    centers_data: list,
    hierarchy_df: pd.DataFrame = None
) -> list:
    """
    Group KPI Centers by hierarchy for display.
    
    Returns list of groups, each containing:
    - parent: The parent center data (or None for roots)
    - children: List of child center data
    
    Structure:
    - Root nodes displayed first
    - Then each parent with its children grouped together
    """
    if not centers_data:
        return []
    
    # Build parent_id lookup from hierarchy_df if available
    parent_map = {}
    if hierarchy_df is not None and not hierarchy_df.empty:
        for _, row in hierarchy_df.iterrows():
            kpc_id = row.get('kpi_center_id')
            parent_id = row.get('parent_center_id')
            if kpc_id is not None:
                parent_map[kpc_id] = parent_id if pd.notna(parent_id) else None
    
    # Build lookup by kpi_center_id
    centers_by_id = {c['kpi_center_id']: c for c in centers_data}
    
    # Find roots (no parent or parent not in current set)
    roots = []
    children_by_parent = {}
    
    for center in centers_data:
        kpc_id = center['kpi_center_id']
        parent_id = parent_map.get(kpc_id) or center.get('parent_center_id')
        
        if parent_id is None or parent_id not in centers_by_id:
            # This is a root in current context
            roots.append(center)
        else:
            # This is a child
            if parent_id not in children_by_parent:
                children_by_parent[parent_id] = []
            children_by_parent[parent_id].append(center)
    
    # Sort roots by level, then name
    roots.sort(key=lambda x: (x.get('level', 0), x.get('kpi_center_name', '')))
    
    # Build result with recursive grouping
    result = []
    
    def add_center_with_children(center, indent_level=0):
        """Recursively add center and its children."""
        center_copy = center.copy()
        center_copy['_indent_level'] = indent_level
        result.append(center_copy)
        
        # Add children sorted by name
        children = children_by_parent.get(center['kpi_center_id'], [])
        children.sort(key=lambda x: x.get('kpi_center_name', ''))
        
        for child in children:
            add_center_with_children(child, indent_level + 1)
    
    for root in roots:
        add_center_with_children(root, 0)
    
    return result


# =============================================================================
# KPI ASSIGNMENTS FRAGMENT (My KPIs Tab) - UPDATED v3.2.0
# =============================================================================

@st.fragment
def kpi_assignments_fragment(
    rollup_targets: Dict,
    hierarchy_df: pd.DataFrame = None,
    fragment_key: str = "kpc_assignments"
):
    """
    KPI Assignments fragment with hierarchy rollup support.
    
    UPDATED v3.2.0: Shows targets for all KPI Centers with hierarchy rollup.
    - Leaf nodes: Direct assignments with weight
    - Parent nodes: Aggregated from all descendants (+ own direct if any)
    
    Args:
        rollup_targets: Dict from metrics.calculate_rollup_targets()
        hierarchy_df: For level filtering (optional)
        fragment_key: Unique key prefix for widgets
    """
    if not rollup_targets:
        st.info("📋 No KPI assignments found for selected KPI Centers and year")
        return
    
    # Help popover
    col_title, col_help = st.columns([6, 1])
    with col_help:
        with st.popover("ℹ️"):
            st.markdown("""
**📊 KPI Assignments Explained**

**🎯 Direct Assignment**
KPIs assigned directly to this KPI Center.
Weight % is used for calculating Overall Achievement.

**📁 Rollup**
Aggregated KPI targets from all child KPI Centers.
Formula: `Parent Target = Sum(All Descendants' Targets)`

**📁 Mixed**
This KPI Center has both direct assignments AND child centers.
Targets shown are: `Direct + Sum(Children)`

**Format Notes**
- Currency values: Rounded to nearest dollar
- Counts: 1 decimal if value < 10
            """)
    
    # Level filter
    if hierarchy_df is not None and 'level' in hierarchy_df.columns:
        levels = sorted(hierarchy_df['level'].unique())
        level_options = ['All Levels'] + [f"Level {l}" for l in levels] + ['Leaf Only']
        selected_level = st.selectbox(
            "Filter by Level",
            level_options,
            key=f"{fragment_key}_level_filter"
        )
    else:
        selected_level = 'All Levels'
    
    # Sort by level for hierarchy display
    sorted_centers = sorted(
        rollup_targets.values(),
        key=lambda x: (x.get('level', 0), x.get('kpi_center_name', ''))
    )
    
    # Filter by level
    if selected_level != 'All Levels':
        if selected_level == 'Leaf Only':
            sorted_centers = [c for c in sorted_centers if c.get('is_leaf', True)]
        else:
            level_num = int(selected_level.split(' ')[1])
            sorted_centers = [c for c in sorted_centers if c.get('level', 0) == level_num]
    
    if not sorted_centers:
        st.info("No KPI Centers found for selected level")
        return
    
    # v5.3.0: Apply hierarchy grouping for better organization
    sorted_centers = build_hierarchy_groups(sorted_centers, hierarchy_df)
    
    # Display each KPI Center
    for center_data in sorted_centers:
        kpi_center_name = center_data['kpi_center_name']
        source = center_data['source']
        level = center_data.get('level', 0)
        is_leaf = center_data.get('is_leaf', True)
        children_count = center_data.get('children_count', 0)
        children_names = center_data.get('children_names', [])
        targets = center_data.get('targets', [])
        indent_level = center_data.get('_indent_level', 0)
        
        # v5.3.0: Use consistent icons with kpi_center_selector
        icon = get_kpi_center_icon(level, is_leaf)
        
        # Badge based on source type
        if source == 'Direct':
            badge = ""
        elif source == 'Rollup':
            badge = f" (Rollup from {children_count} centers)"
        else:  # Mixed
            badge = f" (Mixed: Direct + {children_count} children)"
        
        # Visual indentation based on hierarchy position
        indent = "　" * indent_level  # Use em-space for better visual
        
        with st.expander(f"{indent}{icon} {kpi_center_name}{badge}", expanded=(indent_level == 0 or is_leaf)):
            if not targets:
                st.caption("No KPIs assigned")
                continue
            
            # Build display dataframe
            display_data = []
            for t in targets:
                annual = t.get('annual_target', 0)
                monthly = t.get('monthly_target', annual / 12 if annual else 0)
                quarterly = t.get('quarterly_target', annual / 4 if annual else 0)
                is_currency = t.get('is_currency', False)
                
                # Format values
                if is_currency:
                    annual_str = f"${annual:,.0f}" if annual else "-"
                    monthly_str = f"${monthly:,.0f}" if monthly else "-"
                    quarterly_str = f"${quarterly:,.0f}" if quarterly else "-"
                else:
                    annual_str = f"{annual:,.1f}" if annual and annual < 10 else f"{annual:,.0f}" if annual else "-"
                    monthly_str = f"{monthly:,.2f}" if monthly and monthly < 1 else f"{monthly:,.1f}" if monthly else "-"
                    quarterly_str = f"{quarterly:,.1f}" if quarterly else "-"
                
                row = {
                    'KPI': t.get('display_name', ''),
                    'Annual Target': annual_str,
                    'Monthly': monthly_str,
                    'Quarterly': quarterly_str,
                    'Unit': t.get('unit', ''),
                }
                
                # Weight only for direct assignments
                if source == 'Direct' and t.get('weight') is not None:
                    row['Weight %'] = f"{t['weight']:.0f}%"
                
                display_data.append(row)
            
            # Create dataframe
            display_df = pd.DataFrame(display_data)
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )
            
            # Show children names for rollup
            if children_names and source in ['Rollup', 'Mixed']:
                children_str = ', '.join(children_names[:5])
                if len(children_names) > 5:
                    children_str += f" +{len(children_names) - 5} more"
                st.caption(f"ℹ️ Aggregated from: {children_str}")


# =============================================================================
# KPI PROGRESS FRAGMENT (Progress Tab) - UPDATED v3.3.0
# =============================================================================

@st.fragment
def kpi_progress_fragment(
    progress_data: Dict,
    hierarchy_df: pd.DataFrame = None,
    period_type: str = 'YTD',
    year: int = None,
    fragment_key: str = "kpc_progress"
):
    """
    KPI Progress fragment with per-center breakdown.
    
    UPDATED v3.3.0: Parents now show aggregated KPIs with target-proportion weights.
    - Leaf nodes: Direct KPI progress with individual metrics
    - Parent nodes: Aggregated KPIs from all descendants with derived weights
    
    Args:
        progress_data: Dict from metrics.calculate_per_center_progress()
        hierarchy_df: For level info and filtering
        period_type: Current period type for display
        year: Current year
        fragment_key: Unique key prefix
    """
    if not progress_data:
        st.info("📊 No KPI progress data available")
        return
    
    # Help popover - UPDATED v5.0.0
    col_title, col_help = st.columns([6, 1])
    with col_help:
        with st.popover("ℹ️ How it works"):
            st.markdown(f"""
**📈 KPI Progress Calculation**

---

**🎯 Scenario A: Centers with Direct Assignment**

Each KPI has its own target and **assigned weight** from `sales_kpi_center_assignments`.

`Achievement = Actual / Prorated Target × 100`

`Overall = Σ(KPI Achievement × Assigned Weight) / Σ(Assigned Weights)`

---

**📁 Scenario B: Parent Centers (Rollup)**

Parent centers WITHOUT direct assignment aggregate from children using **default_weight** from `kpi_types`.

**Step 1:** Aggregate targets & actuals by KPI type from all descendants

⚠️ **Important:** Only children with target for each specific KPI contribute.

**Step 2:** Calculate Achievement per KPI

`KPI Achievement = Total Actual / Total Prorated Target × 100`

**Step 3:** Apply Default Weight from `kpi_types`

| KPI Type | Default Weight |
|----------|----------------|
| gross_profit_1 (GP1) | 100 |
| gross_profit | 95 |
| revenue | 90 |
| purchase_value | 80 |
| new_business_revenue | 75 |
| num_new_customers | 60 |
| num_new_combos | 55 |
| num_new_products | 50 |
| num_new_projects | 50 |

*Note: KPIs displayed in order of weight (highest first)*

**Step 4:** Calculate Overall

`Overall = Σ(KPI Achievement × Default Weight) / Σ(Default Weights)`

---

**Prorated Target** ({period_type} {year}):

| Period | Formula |
|--------|---------|
| YTD | Annual × (Days Elapsed / 365) |
| QTD | Annual / 4 |
| MTD | Annual / 12 |
| LY | Full Annual Target |
| Custom | Annual × (Days in Range / 365) |

---

**Achievement Colors:**
- ✅ Green: ≥ 100%
- 🟡 Yellow: 80-99%
- 🔴 Red: < 80%
            """)
    
    # View filter
    view_options = ['All KPI Centers', 'Leaf Only', 'Parents Only']
    selected_view = st.selectbox(
        "View",
        view_options,
        key=f"{fragment_key}_view"
    )
    
    # Filter by view first
    filtered_centers = list(progress_data.values())
    if selected_view == 'Leaf Only':
        filtered_centers = [c for c in filtered_centers if c.get('is_leaf', True)]
    elif selected_view == 'Parents Only':
        filtered_centers = [c for c in filtered_centers if not c.get('is_leaf', True)]
    
    if not filtered_centers:
        st.info("No KPI Centers found for selected view")
        return
    
    # v5.3.0: Group by hierarchy for better visualization
    # Uses build_hierarchy_groups() to arrange: parent → children
    sorted_centers = build_hierarchy_groups(filtered_centers, hierarchy_df)
    
    # Display each KPI Center with hierarchy grouping
    for center_data in sorted_centers:
        kpi_center_id = center_data['kpi_center_id']
        kpi_center_name = center_data['kpi_center_name']
        level = center_data.get('level', 0)
        is_leaf = center_data.get('is_leaf', True)
        overall = center_data.get('overall')
        source = center_data.get('source', 'Direct')
        kpis = center_data.get('kpis', [])
        indent_level = center_data.get('_indent_level', 0)
        
        # v5.3.0: Use consistent icons with kpi_center_selector
        icon = get_kpi_center_icon(level, is_leaf)
        
        # Visual indent based on hierarchy position
        indent_str = "&nbsp;&nbsp;&nbsp;&nbsp;" * indent_level
        
        # Overall badge
        if overall is not None:
            if overall >= 100:
                overall_badge = f"✅ {overall:.1f}%"
                badge_type = "success"
            elif overall >= 80:
                overall_badge = f"🟡 {overall:.1f}%"
                badge_type = "warning"
            else:
                overall_badge = f"🔴 {overall:.1f}%"
                badge_type = "error"
        else:
            overall_badge = "N/A"
            badge_type = "off"
        
        # Header with overall - different sizes based on indent
        if indent_level == 0:
            st.markdown(f"### {icon} {kpi_center_name}")
        elif indent_level == 1:
            st.markdown(f"#### {indent_str}{icon} {kpi_center_name}", unsafe_allow_html=True)
        else:
            st.markdown(f"##### {indent_str}{icon} {kpi_center_name}", unsafe_allow_html=True)
        
        # Overall achievement metric
        col_overall, col_spacer = st.columns([2, 4])
        with col_overall:
            if badge_type == "success":
                st.success(f"⭐ Overall: {overall_badge}")
            elif badge_type == "warning":
                st.warning(f"⭐ Overall: {overall_badge}")
            elif badge_type == "error":
                st.error(f"⭐ Overall: {overall_badge}")
            else:
                st.info(f"⭐ Overall: {overall_badge}")
        
        # Show source indicator for parents
        if not is_leaf:
            children_count = center_data.get('children_count', 0)
            calculation_method = center_data.get('calculation_method', 'default_weight')
            if calculation_method == 'assigned_weight':
                st.caption(f"🎯 Direct assignment | Weight: Assigned")
            else:
                st.caption(f"📊 Rollup from {children_count} child KPI Centers | Weight: Default (from kpi_types)")
        
        # Show KPI progress for BOTH leaf and parent nodes (NEW v3.3.0)
        # UPDATED v5.2.1: KPIs pre-sorted by weight in metrics.py
        if kpis:
            # Ensure sorted by weight (highest first) for display
            sorted_kpis = sorted(kpis, key=lambda x: -x.get('weight', 0))
            for kpi in sorted_kpis:
                display_name = kpi.get('display_name', '')
                actual = kpi.get('actual', 0)
                prorated_target = kpi.get('prorated_target', 0)
                annual_target = kpi.get('annual_target', 0)
                achievement = kpi.get('achievement', 0)
                weight = kpi.get('weight', 100)
                is_currency = kpi.get('is_currency', False)
                weight_source = kpi.get('weight_source', 'assigned')
                contributing_centers = kpi.get('contributing_centers', 0)  # NEW v3.3.1
                
                # Format values
                if is_currency:
                    actual_str = f"${actual:,.0f}"
                    prorated_str = f"${prorated_target:,.0f}"
                    annual_str = f"${annual_target:,.0f}"
                else:
                    actual_str = f"{actual:,.1f}" if actual < 10 else f"{actual:,.0f}"
                    prorated_str = f"{prorated_target:,.1f}" if prorated_target < 10 else f"{prorated_target:,.0f}"
                    annual_str = f"{annual_target:,.0f}"
                
                # KPI name with weight - show weight source
                weight_source = kpi.get('weight_source', 'assigned')
                if weight_source == 'default':
                    st.markdown(f"**{display_name}** ({weight:.0f} default)")
                else:
                    st.markdown(f"**{display_name}** ({weight:.0f}%)")
                
                # Progress bar
                progress_value = min(achievement / 100, 1.0) if achievement > 0 else 0
                st.progress(progress_value)
                
                # Details - UPDATED v3.3.1: Show contributing centers count
                if not is_leaf:
                    children_count = center_data.get('children_count', 0)
                    if contributing_centers > 0 and contributing_centers < children_count:
                        # Not all children have this KPI target
                        st.caption(f"{actual_str} / {prorated_str} prorated ({annual_str} annual) — From {contributing_centers} of {children_count} centers with this target")
                    else:
                        st.caption(f"{actual_str} / {prorated_str} prorated ({annual_str} annual) — From {contributing_centers} centers")
                else:
                    st.caption(f"{actual_str} / {prorated_str} prorated ({annual_str} annual)")
                
                # Achievement badge
                col_badge, _ = st.columns([1, 5])
                with col_badge:
                    if achievement >= 100:
                        st.success(f"✅ {achievement:.1f}%")
                    elif achievement >= 80:
                        st.warning(f"🟡 {achievement:.1f}%")
                    else:
                        st.error(f"🔴 {achievement:.1f}%")
        
        # For parent nodes: show children summary in expander (optional detail)
        if not is_leaf:
            children_summary = center_data.get('children_summary', [])
            
            if children_summary:
                with st.expander(f"👥 View {len(children_summary)} Child KPI Centers"):
                    # Create summary table
                    summary_data = []
                    for child in children_summary:
                        ach = child.get('achievement')
                        ach_str = f"{ach:.1f}%" if ach is not None else "N/A"
                        summary_data.append({
                            'KPI Center': child.get('name', ''),
                            'Overall Achievement': ach_str,
                        })
                    
                    summary_df = pd.DataFrame(summary_data)
                    st.dataframe(
                        summary_df,
                        use_container_width=True,
                        hide_index=True,
                        height=min(200, len(summary_data) * 35 + 40)
                    )
        
        st.markdown("---")


# =============================================================================
# KPI CENTER RANKING FRAGMENT - UPDATED v3.2.0 with level grouping
# =============================================================================

@st.fragment
def kpi_center_ranking_fragment(
    ranking_df: pd.DataFrame,
    progress_data: Dict = None,
    hierarchy_df: pd.DataFrame = None,
    show_targets: bool = True,
    fragment_key: str = "kpc_ranking"
):
    """
    KPI Center performance ranking table with hierarchy level grouping.
    
    UPDATED v3.2.0: Group by hierarchy level for fair comparison.
    - Only shows levels with ≥2 items
    - Medals for top 3 within each level
    
    Args:
        ranking_df: Sales summary by KPI Center
        progress_data: Dict from metrics.calculate_per_center_progress() for overall achievement
        hierarchy_df: With level info for grouping
        show_targets: Whether to show achievement column
        fragment_key: Unique key prefix
    """
    if ranking_df.empty:
        st.info("No ranking data available")
        return
    
    # Help popover
    col_title, col_help = st.columns([6, 1])
    with col_help:
        with st.popover("ℹ️"):
            st.markdown("""
**🏆 Ranking Explained**

**Why Group by Level?**

KPI Centers have different scopes:
- **Level 0/1**: Regional (aggregate multiple sub-regions)
- **Level 2+**: Individual markets
- **Leaf**: Smallest units

Comparing ALL together isn't fair because 
parent totals include children's data.

**By grouping by level**, we compare:
- Parents with parents
- Leaves with leaves

**Achievement %**: 
- Leaf: Weighted average of KPI achievements
- Parent: Weighted average of children's achievements
            """)
    
    # Rank by dropdown
    sort_options = ['KPI Achievement %', 'Revenue', 'Gross Profit', 'GP1', 'GP %', 'Customers']
    if not show_targets or progress_data is None:
        sort_options.remove('KPI Achievement %')
    
    col_rank, col_level = st.columns(2)
    
    with col_rank:
        sort_by = st.selectbox(
            "📊 Rank by",
            sort_options,
            key=f"{fragment_key}_sort"
        )
    
    # Level filter
    with col_level:
        if hierarchy_df is not None and 'level' in hierarchy_df.columns:
            levels = sorted(hierarchy_df['level'].unique())
            level_options = ['All (grouped)'] + [f"Level {l}" for l in levels] + ['Leaf Only']
            selected_level = st.selectbox(
                "🏷️ Level",
                level_options,
                key=f"{fragment_key}_level"
            )
        else:
            selected_level = 'All (grouped)'
    
    # Merge progress data into ranking_df
    if progress_data:
        ranking_df = ranking_df.copy()
        ranking_df['overall_achievement'] = ranking_df['kpi_center_id'].apply(
            lambda x: progress_data.get(x, {}).get('overall')
        )
    
    # Merge hierarchy data
    if hierarchy_df is not None:
        ranking_df = ranking_df.merge(
            hierarchy_df[['kpi_center_id', 'level', 'is_leaf']],
            on='kpi_center_id',
            how='left'
        )
    else:
        ranking_df['level'] = 0
        ranking_df['is_leaf'] = 1
    
    # Map sort selection
    sort_col_map = {
        'KPI Achievement %': 'overall_achievement',
        'Revenue': 'revenue',
        'Gross Profit': 'gross_profit',
        'GP1': 'gp1',
        'GP %': 'gp_percent',
        'Customers': 'customers'
    }
    sort_col = sort_col_map.get(sort_by, 'revenue')
    
    if sort_col not in ranking_df.columns:
        sort_col = 'revenue'
    
    # Column config - use TextColumn for pre-formatted values
    column_config = {
        'Rank': st.column_config.TextColumn('Rank', width='small'),
        'kpi_center': st.column_config.TextColumn('KPI Center', width='medium'),
        'revenue_fmt': st.column_config.TextColumn('Revenue', width='small'),
        'gross_profit_fmt': st.column_config.TextColumn('Gross Profit', width='small'),
        'gp1_fmt': st.column_config.TextColumn('GP1', width='small'),
        'gp_percent': st.column_config.NumberColumn('GP %', format='%.1f%%'),
        'customers': st.column_config.NumberColumn('Customers', format='%d'),
    }
    
    if progress_data and 'overall_achievement' in ranking_df.columns:
        column_config['overall_achievement'] = st.column_config.ProgressColumn(
            'Achievement %',
            min_value=0,
            max_value=150,
            format='%.1f%%'
        )
    
    display_cols = ['Rank', 'kpi_center', 'revenue_fmt', 'gross_profit_fmt', 'gp1_fmt', 'gp_percent', 'customers']
    if progress_data and 'overall_achievement' in ranking_df.columns:
        display_cols.append('overall_achievement')
    
    available_cols = [c for c in display_cols if c in ranking_df.columns or c.replace('_fmt', '') in ranking_df.columns]
    
    # Filter and display by level
    if selected_level == 'All (grouped)':
        # Group by level
        levels = sorted(ranking_df['level'].dropna().unique())
        
        for level in levels:
            level_df = ranking_df[ranking_df['level'] == level].copy()
            
            # Only show levels with ≥2 items (to rank)
            if len(level_df) < 2:
                continue
            
            # Sort and rank within level
            level_df = level_df.sort_values(sort_col, ascending=False, na_position='last')
            level_df.insert(0, 'Rank', [get_rank_display(i) for i in range(1, len(level_df) + 1)])
            
            # Format currency columns
            if 'revenue' in level_df.columns:
                level_df['revenue_fmt'] = level_df['revenue'].apply(format_currency)
            if 'gross_profit' in level_df.columns:
                level_df['gross_profit_fmt'] = level_df['gross_profit'].apply(format_currency)
            if 'gp1' in level_df.columns:
                level_df['gp1_fmt'] = level_df['gp1'].apply(format_currency)
            
            # Level header
            is_leaf_level = level_df['is_leaf'].iloc[0] == 1 if 'is_leaf' in level_df.columns else False
            level_label = "Leaf" if is_leaf_level else f"Level {int(level)}"
            
            st.markdown(f"##### 📁 {level_label} ({len(level_df)} KPI Centers)")
            
            # Get available columns for this dataframe
            df_available_cols = [c for c in display_cols if c in level_df.columns]
            
            st.dataframe(
                level_df[df_available_cols],
                hide_index=True,
                column_config=column_config,
                use_container_width=True
            )
            
            st.markdown("")  # Spacing
        
    else:
        # Single level view
        if selected_level == 'Leaf Only':
            filtered_df = ranking_df[ranking_df['is_leaf'] == 1].copy()
            level_label = "Leaf"
        else:
            level_num = int(selected_level.split(' ')[1])
            filtered_df = ranking_df[ranking_df['level'] == level_num].copy()
            level_label = f"Level {level_num}"
        
        if filtered_df.empty:
            st.info(f"No KPI Centers found for {level_label}")
            return
        
        if len(filtered_df) < 2:
            st.warning(f"Only {len(filtered_df)} KPI Center at {level_label}. Need ≥2 to rank.")
        
        # Sort and rank
        filtered_df = filtered_df.sort_values(sort_col, ascending=False, na_position='last')
        filtered_df.insert(0, 'Rank', [get_rank_display(i) for i in range(1, len(filtered_df) + 1)])
        
        # Format currency columns
        if 'revenue' in filtered_df.columns:
            filtered_df['revenue_fmt'] = filtered_df['revenue'].apply(format_currency)
        if 'gross_profit' in filtered_df.columns:
            filtered_df['gross_profit_fmt'] = filtered_df['gross_profit'].apply(format_currency)
        if 'gp1' in filtered_df.columns:
            filtered_df['gp1_fmt'] = filtered_df['gp1'].apply(format_currency)
        
        # Get available columns for this dataframe
        df_available_cols = [c for c in display_cols if c in filtered_df.columns]
        
        st.dataframe(
            filtered_df[df_available_cols],
            hide_index=True,
            column_config=column_config,
            use_container_width=True
        )
    
    # Footer
    st.caption(f"⭐ Ranked by **{sort_by}** (highest first)")