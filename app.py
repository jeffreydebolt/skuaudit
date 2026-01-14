import streamlit as st
import pandas as pd
from datetime import datetime
import os

# Must be first Streamlit command
st.set_page_config(page_title="SKUaudit", page_icon="📊", layout="wide")

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


def run_audit(results):
    """Run the margin audit and display results"""
    
    st.markdown("---")
    
    if st.button("🔍 Run Audit", type="primary", use_container_width=True):
        
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
        
        # Display results
        st.markdown("### 📊 Audit Results")
        
        # Summary metrics - based on MARGIN (the bottom line)
        above = len(results_with_costs[results_with_costs['margin_pct'] >= MARGIN_ELITE])
        typical = len(results_with_costs[(results_with_costs['margin_pct'] >= MARGIN_DANGER) & (results_with_costs['margin_pct'] < MARGIN_ELITE)])
        below = len(results_with_costs[results_with_costs['margin_pct'] < MARGIN_DANGER])
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total SKUs", len(results_with_costs))
        col2.metric("🟢 Above Benchmark", above)
        col3.metric("🟡 Typical", typical)
        col4.metric("🔴 Below Benchmark", below)
        
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
            if row['Recommendation'] != "✓ Solid margins":
                st.info(f"**{row['SKU']}**: {row['Recommendation']}")
            else:
                st.success(f"**{row['SKU']}**: {row['Recommendation']}")
        
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
    """Generate recommendations based on flags"""
    recs = []
    
    if row['fulfillment_pct'] >= FULFILLMENT_DANGER:
        recs.append(f"Fulfillment {row['fulfillment_pct']:.1f}% (typical: {FULFILLMENT_MEDIAN}%) - check dimensions, packaging, or pricing")
    
    if row['cogs_pct'] >= COGS_DANGER:
        recs.append(f"COGS {row['cogs_pct']:.1f}% (typical: {COGS_MEDIAN}%) - review supplier costs or pricing")
    
    if row['margin_pct'] < MARGIN_DANGER:
        recs.append(f"Margin {row['margin_pct']:.1f}% below benchmark ({MARGIN_MEDIAN}%) - review unit economics")
    
    return " | ".join(recs) if recs else "✓ Solid margins"


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
        
        # SKU limit for free tier
        if len(results) > FREE_SKU_LIMIT:
            st.warning(f"Free tier is limited to {FREE_SKU_LIMIT} SKUs. You have {len(results)}.")
            
            sku_choice = st.radio(
                "Choose an option:",
                [f"Audit first {FREE_SKU_LIMIT} SKUs (free)", "Unlock all SKUs ($29 one-time)"],
                horizontal=True
            )
            
            if "Unlock" in sku_choice:
                st.info("💳 Payment coming soon. For now, email hello@skuaudit.com for early access to unlimited audits.")
                st.stop()
            else:
                results = results.head(FREE_SKU_LIMIT).copy()
                st.caption(f"Showing first {FREE_SKU_LIMIT} SKUs")
        
        st.markdown("### Step 2: Add Your Landed Costs")
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
    2. **Enter** your landed cost for each SKU (manually or via CSV)
    3. **See** instant margin analysis with color-coded flags
    4. **Get** specific recommendations for problem SKUs
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
