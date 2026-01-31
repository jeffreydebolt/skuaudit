import streamlit as st
import pandas as pd
from datetime import datetime
import os
import re

# Must be first Streamlit command
st.set_page_config(page_title="SKUaudit", page_icon="📊", layout="wide")

# Hide Streamlit branding
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# Optional: Supabase for storing anonymized benchmark data
try:
    from supabase import create_client, Client
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
    if SUPABASE_URL and SUPABASE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        DB_ENABLED = True
    else:
        DB_ENABLED = False
except:
    DB_ENABLED = False

# Session state initialization
if 'email_submitted' not in st.session_state:
    st.session_state.email_submitted = False
if 'lead_email' not in st.session_state:
    st.session_state.lead_email = ""
if 'last_upload_name' not in st.session_state:
    st.session_state.last_upload_name = ""
if 'audit_triggered' not in st.session_state:
    st.session_state.audit_triggered = False
if 'sku_selections' not in st.session_state:
    st.session_state.sku_selections = {}


def save_anonymized_data(results_df):
    """Save anonymized SKU data to improve benchmarks over time"""
    if not DB_ENABLED:
        return

    try:
        for _, row in results_df.iterrows():
            # Only store anonymized metrics - no identifiers
            data = {
                "price_tier": categorize_price(row['Price']),
                "fulfillment_pct": round(row['fulfillment_pct'], 1),
                "cogs_pct": round(row['cogs_pct'], 1),
                "margin_pct": round(row['margin_pct'], 1),
                "created_at": datetime.utcnow().isoformat()
            }
            supabase.table("benchmark_data").insert(data).execute()
    except Exception as e:
        # Silently fail - don't break the app if DB fails
        pass


def save_lead(email, first_name, brand_name, sku_count):
    """Save lead data to Supabase"""
    if not DB_ENABLED:
        return
    try:
        data = {
            "email": email,
            "first_name": first_name if first_name else None,
            "brand_name": brand_name if brand_name else None,
            "sku_count": sku_count,
            "created_at": datetime.utcnow().isoformat()
        }
        supabase.table("leads").insert(data).execute()
    except Exception:
        pass


def categorize_price(price):
    """Categorize price into tiers for anonymous benchmarking"""
    if price < 15:
        return "under_15"
    elif price < 25:
        return "15_to_25"
    elif price < 50:
        return "25_to_50"
    elif price < 100:
        return "50_to_100"
    else:
        return "over_100"


def is_junk_sku(sku):
    """Heuristic to detect junk/test/placeholder SKUs created by Amazon for returns"""
    sku_str = str(sku).strip()
    # Long random-looking alphanumeric string (no dashes/structure, >20 chars)
    if len(sku_str) > 20 and re.match(r'^[A-Za-z0-9]+$', sku_str):
        return True
    # Purely numeric and very long (likely internal ID)
    if len(sku_str) > 15 and sku_str.isdigit():
        return True
    return False


def find_duplicate_products(df):
    """Find SKUs with identical product name AND price (likely return duplicates)"""
    if 'Product' not in df.columns:
        return set()
    dupes = set()
    grouped = df.groupby(['Product', 'Price'])
    for _, group in grouped:
        if len(group) > 1:
            # Flag all but the first as potential duplicates
            dupe_skus = group['SKU'].iloc[1:].tolist()
            dupes.update(dupe_skus)
    return dupes


def run_audit(results):
    """Run the margin audit and display results"""

    # --- EMAIL GATE (before showing results) ---
    if DB_ENABLED and not st.session_state.get('email_submitted', False):
        st.markdown("---")
        st.markdown("### Enter your email to see results")
        st.caption("We'll send you a PDF of your results. No spam.")

        with st.form("email_gate_form"):
            email = st.text_input("Email *", placeholder="you@company.com")
            first_name = st.text_input("First Name (optional)")
            brand_name = st.text_input("Company / Brand (optional)")
            submitted = st.form_submit_button("Show My Results", type="primary", use_container_width=True)

            if submitted:
                if not email or '@' not in email:
                    st.error("Please enter a valid email address.")
                else:
                    save_lead(email, first_name, brand_name, len(results))
                    st.session_state.email_submitted = True
                    st.session_state.lead_email = email
                    st.rerun()

        return  # Block results until email is submitted

    st.markdown("---")

    if st.button("🔍 Run Audit", type="primary", use_container_width=True):
        st.session_state.audit_triggered = True

    if st.session_state.get('audit_triggered', False):

        # Filter to only SKUs with costs entered
        results_with_costs = results[results['Landed Cost'] > 0].copy()

        if len(results_with_costs) == 0:
            st.error("Please enter landed costs for at least one SKU")
            return

        # Calculate percentages
        results_with_costs['fulfillment_pct'] = (results_with_costs['Fulfillment Fee'] / results_with_costs['Price']) * 100
        results_with_costs['cogs_pct'] = (results_with_costs['Landed Cost'] / results_with_costs['Price']) * 100
        results_with_costs['margin'] = results_with_costs['Price'] - results_with_costs['Total Amazon Fees'] - results_with_costs['Landed Cost']
        results_with_costs['margin_pct'] = (results_with_costs['margin'] / results_with_costs['Price']) * 100

        # Add status flags
        results_with_costs['Fulfillment Status'] = results_with_costs['fulfillment_pct'].apply(
            lambda x: get_status(x, FULFILLMENT_ELITE, FULFILLMENT_MEDIAN, FULFILLMENT_DANGER, higher_is_better=False)
        )
        results_with_costs['COGS Status'] = results_with_costs['cogs_pct'].apply(
            lambda x: get_status(x, COGS_ELITE, COGS_MEDIAN, COGS_DANGER, higher_is_better=False)
        )
        results_with_costs['Margin Status'] = results_with_costs['margin_pct'].apply(
            lambda x: get_status(x, MARGIN_ELITE, MARGIN_MEDIAN, MARGIN_DANGER, higher_is_better=True)
        )

        # Add recommendations
        results_with_costs['Recommendation'] = results_with_costs.apply(get_recommendation, axis=1)

        # Sort by margin ascending (worst first)
        results_with_costs = results_with_costs.sort_values('margin_pct', ascending=True)

        # Display results
        st.markdown("### 📊 Audit Results")

        # Summary metrics - based on MARGIN (the bottom line)
        above = len(results_with_costs[results_with_costs['margin_pct'] >= MARGIN_ELITE])
        typical = len(results_with_costs[(results_with_costs['margin_pct'] >= MARGIN_DANGER) & (results_with_costs['margin_pct'] < MARGIN_ELITE)])
        below = len(results_with_costs[results_with_costs['margin_pct'] < MARGIN_DANGER])
        issues = len(results_with_costs[results_with_costs['margin_pct'] < MARGIN_DANGER])

        # Estimated margin opportunity: how much margin improves if below-median SKUs reach median
        opportunity = 0.0
        below_median = results_with_costs[results_with_costs['margin_pct'] < MARGIN_MEDIAN]
        for _, row in below_median.iterrows():
            target_margin = row['Price'] * (MARGIN_MEDIAN / 100)
            current_margin = row['margin']
            opportunity += max(0, target_margin - current_margin)

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total SKUs", len(results_with_costs))
        col2.metric("🟢 Above Benchmark", above)
        col3.metric("🟡 Typical", typical)
        col4.metric("🔴 Below Benchmark", below)
        col5.metric("⚠️ Potential Issues", issues)

        if opportunity > 0:
            st.info(f"💰 **Estimated margin opportunity: ${opportunity:.2f}/unit** if below-benchmark SKUs reached median performance.")

        st.markdown("---")

        # Detailed results table - clean with status indicators
        display_df = pd.DataFrame({
            'SKU': results_with_costs['SKU'],
            'Price': results_with_costs['Price'].apply(lambda x: f"${x:.2f}"),
            'Fulfillment %': results_with_costs.apply(lambda r: f"{r['Fulfillment Status']} {r['fulfillment_pct']:.1f}%", axis=1),
            'COGS %': results_with_costs.apply(lambda r: f"{r['COGS Status']} {r['cogs_pct']:.1f}%", axis=1),
            'Margin %': results_with_costs.apply(lambda r: f"{r['Margin Status']} {r['margin_pct']:.1f}%", axis=1),
        })

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Download results
        csv_results = display_df.to_csv(index=False)
        st.download_button(
            "📥 Download Results (CSV)",
            csv_results,
            "skuaudit_results.csv",
            "text/csv"
        )

        # Recommendations
        st.markdown("### 💡 Recommendations")

        for _, row in results_with_costs.iterrows():
            rec = row['Recommendation']
            if rec.startswith("✅"):
                st.success(f"**{row['SKU']}**: {rec}")
            elif rec.startswith("⚠️") or "Negative margin" in rec:
                st.error(f"**{row['SKU']}**: {rec}")
            elif rec == "✓ Solid margins — within benchmark range.":
                st.success(f"**{row['SKU']}**: {rec}")
            else:
                st.info(f"**{row['SKU']}**: {rec}")

        # What's Next? section
        st.markdown("---")
        st.markdown("### What's Next?")
        st.markdown("""
This audit covers margins from your Fee Preview data. For a complete picture, you'd also want:
- 📊 **Ad spend by SKU** — are you spending more on ads than you're making?
- 📦 **Inventory velocity** — how fast does each SKU sell?
- 💰 **Cash conversion cycle** — how long until your inventory investment turns back into cash?

Want the full analysis? [Get in touch](mailto:hello@skuaudit.com)
        """)

        # Benchmarks reference
        with st.expander("📏 Benchmark Reference (2025 Data)"):
            st.markdown("""
            **Fulfillment % of Price:**
            - 🟢 15% or less - Elite (Top 10%)
            - 🟡 16-22% - Typical
            - 🔴 30%+ - Above typical

            **COGS % of Price:**
            - 🟢 19% or less - Elite (Top 10%)
            - 🟡 20-27% - Typical
            - 🔴 33%+ - Above typical

            **Gross Margin %:**
            - 🟢 43%+ - Elite
            - 🟡 28-42% - Typical
            - 🔴 Under 28% - Below typical

            *Based on real data from 7-figure Amazon sellers. These are benchmarks, not rules — your business context matters.*
            """)

        # Data contribution checkbox - after results
        st.markdown("---")
        contribute_data = st.checkbox(
            "✓ Contribute my anonymized data to improve benchmarks",
            value=True,
            help="No product names or identifiers stored. Just price tiers, fee percentages, and margins."
        )

        if contribute_data:
            save_anonymized_data(results_with_costs)
            st.caption("Thanks! Your anonymous data helps improve benchmarks for all sellers.")

        st.markdown("---")
        st.caption("[hello@skuaudit.com](mailto:hello@skuaudit.com)")

st.title("📊 SKUaudit")
st.subheader("Amazon FBA Margin Audit • Benchmarked Against Real Seller Data")

# Thresholds (2025 Benchmarks - real Amazon seller data)
# Note: Amazon takes ~1 margin point/year from sellers
# 2024: fulfillment fee increases, 2025: reimbursement policy changes

FULFILLMENT_ELITE = 15      # Top 10%
FULFILLMENT_MEDIAN = 22     # Median performer (was 20% in 2023)
FULFILLMENT_DANGER = 30     # High/problematic

COGS_ELITE = 19             # Top 10%
COGS_MEDIAN = 27            # Median performer
COGS_DANGER = 33            # High/problematic

MARGIN_ELITE = 43           # Top performers (was 45% in 2023)
MARGIN_MEDIAN = 34          # Median performer (was 36% in 2023)
MARGIN_DANGER = 28          # Below this is trouble

FREE_SKU_LIMIT = 10         # Free tier limit


def get_status(value, elite, median, danger, higher_is_better=True):
    """Return emoji status based on thresholds"""
    if higher_is_better:
        # For margin: higher is better
        if value >= elite:
            return "🟢"
        elif value >= danger:
            return "🟡"
        else:
            return "🔴"
    else:
        # For costs: lower is better
        if value <= elite:
            return "🟢"
        elif value < danger:
            return "🟡"
        else:
            return "🔴"


def get_recommendation(row):
    """Generate CFO-quality diagnostic recommendations"""
    recs = []
    price = row['Price']
    ff_pct = row['fulfillment_pct']
    cogs_pct = row['cogs_pct']
    margin_pct = row['margin_pct']

    # Negative margin — immediate kill candidate
    if margin_pct < 0:
        recs.append(f"⚠️ Negative margin ({margin_pct:.1f}%). This SKU loses money on every sale. Either raise price significantly or discontinue.")
        if price < 15 and ff_pct > 30:
            recs.append(f"At ${price:.2f}, FBA fulfillment fees ({ff_pct:.1f}%) are structurally too high. Consider: raise price above $15, switch to FBM/3PL, or bundle with higher-margin products.")
        return " | ".join(recs)

    # Low price + high fulfillment = structural problem
    if price < 15 and ff_pct > 25:
        recs.append(f"FBA fulfillment at {ff_pct:.1f}% on a ${price:.2f} item is a structural problem — the fee is a fixed dollar amount that doesn't scale with price. Consider raising price above $15 or switching to FBM.")
    elif ff_pct >= 30:
        recs.append(f"Fulfillment at {ff_pct:.1f}% is well above typical (22%). Check product dimensions/weight — even small reductions in package size can drop fees significantly.")
    elif ff_pct >= 25:
        recs.append(f"Fulfillment at {ff_pct:.1f}% is elevated. Review packaging dimensions — Amazon charges by dimensional weight.")

    # High COGS
    if cogs_pct >= 40:
        recs.append(f"COGS at {cogs_pct:.1f}% is very high. Negotiate with supplier, explore alternative sourcing, or raise price to improve the ratio.")
    elif cogs_pct >= 33:
        recs.append(f"COGS at {cogs_pct:.1f}% is above benchmark (27% typical). Review landed cost — are freight, duty, or prep costs inflating this?")

    # Margin assessment
    if margin_pct < 15:
        recs.append(f"Margin at {margin_pct:.1f}% is in the danger zone. This SKU needs a strong volume justification to keep. Without high velocity, it's a discontinuation candidate.")
    elif margin_pct < 28:
        recs.append(f"Margin at {margin_pct:.1f}% is below the typical benchmark (34%). Monitor closely — this SKU has thin room for ad spend.")

    # Good margins — positive reinforcement with insight
    if margin_pct >= 43 and ff_pct <= 18:
        return "✅ Strong margins with efficient fulfillment. This SKU can support advertising investment."
    elif margin_pct >= 43:
        return "✅ Strong margins. Room for ad spend or promotional pricing if needed."

    return " | ".join(recs) if recs else "✓ Solid margins — within benchmark range."


# File upload
st.markdown("### Step 1: Upload Fee Preview Report")

with st.expander("How do I get this report?"):
    st.markdown("""
    1. [**Click here to open Fee Preview in Seller Central**](https://sellercentral.amazon.com/reportcentral/ESTIMATED_FBA_FEES/1)
    2. Click **Request Download**
    3. Wait for report to generate, then download the .txt file
    4. Upload it here
    """)

uploaded_file = st.file_uploader("Upload Fee Preview (.txt or .csv)", type=['txt', 'csv'])

if uploaded_file is not None:
    # Reset flow state on new upload
    if st.session_state.last_upload_name != uploaded_file.name:
        st.session_state.last_upload_name = uploaded_file.name
        st.session_state.email_submitted = False
        st.session_state.lead_email = ""
        st.session_state.audit_triggered = False
        st.session_state.sku_selections = {}

    # Parse the file - handle various encodings
    try:
        df = pd.read_csv(uploaded_file, sep='\t', encoding='utf-8')
    except:
        try:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, sep='\t', encoding='latin-1')
        except:
            try:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding='utf-8')
            except:
                try:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, encoding='latin-1')
                except Exception as e:
                    st.error(f"Could not read file. Try saving as UTF-8 CSV first.")
                    st.stop()

    # Extract relevant columns
    if 'sku' in df.columns and 'sales-price' in df.columns and 'expected-fulfillment-fee-per-unit' in df.columns:

        results = pd.DataFrame({
            'SKU': df['sku'],
            'Product': df['product-name'].str[:50] + '...' if 'product-name' in df.columns else df['sku'],
            'Price': df['sales-price'],
            'Referral Fee': df['estimated-referral-fee-per-unit'],
            'Fulfillment Fee': df['expected-fulfillment-fee-per-unit'],
            'Total Amazon Fees': df['estimated-fee-total']
        })

        st.success(f"✓ Found {len(results)} SKUs")

        # --- SKU SELECTION & FILTERING ---
        st.markdown("### Step 2: Select SKUs to Audit")

        # Detect junk/duplicate SKUs
        junk_skus = set(sku for sku in results['SKU'] if is_junk_sku(sku))
        dupe_skus = find_duplicate_products(results)
        flagged_skus = junk_skus | dupe_skus

        if flagged_skus:
            st.warning(f"Auto-flagged {len(flagged_skus)} suspected junk/duplicate SKUs (deselected by default). Review below.")

        # Initialize selections on first load (all selected except flagged)
        if not st.session_state.sku_selections:
            st.session_state.sku_selections = {
                sku: (sku not in flagged_skus) for sku in results['SKU']
            }

        # Search filter
        search_term = st.text_input("🔍 Search SKUs", placeholder="Type to filter by SKU or product name...")

        # Select All / Deselect All — update session state and rerun
        col_a, col_b, col_c = st.columns([1, 1, 4])
        if col_a.button("Select All"):
            for sku in results['SKU']:
                st.session_state.sku_selections[sku] = True
            st.rerun()
        if col_b.button("Deselect All"):
            for sku in results['SKU']:
                st.session_state.sku_selections[sku] = False
            st.rerun()

        # Build selection dataframe from session state
        selection_df = results[['SKU', 'Product', 'Price']].copy()
        selection_df.insert(0, 'Select', selection_df['SKU'].map(
            lambda s: st.session_state.sku_selections.get(s, True)
        ))

        # Apply search filter for display
        if search_term:
            mask = (
                selection_df['SKU'].str.contains(search_term, case=False, na=False) |
                selection_df['Product'].str.contains(search_term, case=False, na=False)
            )
            display_selection = selection_df[mask].copy()
        else:
            display_selection = selection_df.copy()

        # Editable selection table
        edited_selection = st.data_editor(
            display_selection,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=True),
                "SKU": st.column_config.TextColumn("SKU", disabled=True),
                "Product": st.column_config.TextColumn("Product", disabled=True, width="medium"),
                "Price": st.column_config.NumberColumn("Price", disabled=True, format="$%.2f"),
            },
            hide_index=True,
            use_container_width=True,
            key="sku_selector"
        )

        # Write edits back to session state
        for _, row in edited_selection.iterrows():
            st.session_state.sku_selections[row['SKU']] = bool(row['Select'])

        # Get selected SKUs from session state (full list, not just displayed)
        selected_skus = [sku for sku in results['SKU'] if st.session_state.sku_selections.get(sku, False)]
        selected_count = len(selected_skus)
        total_count = len(results)

        st.markdown(f"**{selected_count} of {total_count} SKUs selected**")

        if selected_count == 0:
            st.info("Select at least one SKU to continue.")
            st.stop()

        # Free tier limit applies to SELECTED SKUs
        if selected_count > FREE_SKU_LIMIT:
            st.warning(f"Free tier is limited to {FREE_SKU_LIMIT} SKUs. You have {selected_count} selected.")

            sku_choice = st.radio(
                "Choose an option:",
                [f"Audit first {FREE_SKU_LIMIT} selected SKUs (free)", "Unlock all SKUs ($29 one-time)"],
                horizontal=True
            )

            if "Unlock" in sku_choice:
                st.info("💳 Payment coming soon. For now, email hello@skuaudit.com for early access to unlimited audits.")
                st.stop()
            else:
                selected_skus = selected_skus[:FREE_SKU_LIMIT]
                st.caption(f"Using first {FREE_SKU_LIMIT} selected SKUs")

        # Filter results to selected SKUs
        results = results[results['SKU'].isin(selected_skus)].copy()

        # --- COST ENTRY ---
        st.markdown("### Step 3: Add Your Landed Costs")
        st.caption("Include product cost, shipping to Amazon, packaging, etc.")

        # Two options for entering costs
        cost_method = st.radio(
            "How do you want to enter costs?",
            ["Enter manually below", "Upload CSV with costs"],
            horizontal=True
        )

        if cost_method == "Upload CSV with costs":
            # Generate template for download
            template_df = results[['SKU', 'Product', 'Price']].copy()
            template_df['Landed Cost'] = ''

            csv_template = template_df.to_csv(index=False)

            st.download_button(
                label="📥 Download CSV Template",
                data=csv_template,
                file_name="skuaudit_costs_template.csv",
                mime="text/csv"
            )

            st.caption("Fill in the 'Landed Cost' column, then upload below:")

            costs_file = st.file_uploader("Upload completed CSV", type=['csv'], key="costs_upload")

            if costs_file is not None:
                costs_df = pd.read_csv(costs_file)

                if 'SKU' in costs_df.columns and 'Landed Cost' in costs_df.columns:
                    # Merge costs with results
                    cost_map = dict(zip(costs_df['SKU'], pd.to_numeric(costs_df['Landed Cost'], errors='coerce').fillna(0)))
                    results['Landed Cost'] = results['SKU'].map(cost_map).fillna(0)

                    filled_count = len(results[results['Landed Cost'] > 0])
                    st.success(f"✓ Loaded costs for {filled_count} of {len(results)} SKUs")

                    if filled_count > 0:
                        run_audit(results)
                else:
                    st.error("CSV must have 'SKU' and 'Landed Cost' columns")

        else:  # Manual entry
            st.markdown("---")

            # Create editable dataframe for cost entry
            edit_df = results[['SKU', 'Product', 'Price']].copy()
            edit_df['Landed Cost'] = 0.0

            edited = st.data_editor(
                edit_df,
                column_config={
                    "SKU": st.column_config.TextColumn("SKU", disabled=True),
                    "Product": st.column_config.TextColumn("Product", disabled=True, width="medium"),
                    "Price": st.column_config.NumberColumn("Price", disabled=True, format="$%.2f"),
                    "Landed Cost": st.column_config.NumberColumn("Landed Cost", format="$%.2f", min_value=0, required=True)
                },
                hide_index=True,
                use_container_width=True
            )

            results['Landed Cost'] = edited['Landed Cost']

            filled_count = len(results[results['Landed Cost'] > 0])

            if filled_count > 0:
                run_audit(results)
            else:
                st.info("👆 Enter your landed cost for each SKU above, then scroll down for results")

    else:
        st.error("Could not find required columns. Make sure this is an Amazon Fee Preview report.")
        st.write("Found columns:", df.columns.tolist())

else:
    # Show example
    st.markdown("---")
    st.markdown("### How it works")
    st.markdown("""
    1. **Upload** your Fee Preview report from Seller Central
    2. **Select** which SKUs to audit (junk SKUs auto-flagged)
    3. **Enter** your landed cost for each SKU (manually or via CSV)
    4. **See** instant margin analysis with color-coded flags
    5. **Get** specific recommendations for problem SKUs
    """)

    st.markdown("---")
    st.caption("Benchmarks based on real 7-figure Amazon seller data")

    with st.expander("🔒 Privacy"):
        st.markdown("""
        **What we collect (if you opt in):**
        - Price tier (e.g., "$25-50" — not exact price)
        - Fulfillment fee %
        - COGS %
        - Margin %

        **What we never collect:**
        - Product names
        - SKUs or ASINs
        - Business name
        - Any identifying information

        Your data helps improve benchmarks for all sellers. You can opt out by unchecking the box before running your audit.

        Questions? [hello@skuaudit.com](mailto:hello@skuaudit.com)
        """)
