"""
🚗 SM360 Dealer Scraper - STREAMLIT UI
======================================
Streamlit interface for the vehicle scraper.

Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from io import BytesIO

# Import from scraper module
from scraper import (
    is_selenium_available,
    parse_urls,
    get_dealer_name,
    scrape_all_vehicles_multi
)


# -------------------------------------------------
# STREAMLIT UI
# -------------------------------------------------
def main():
    st.set_page_config(page_title="Multi-URL Vehicle Scraper(#Lvy)", page_icon="🚗", layout="wide")
    
    st.title("🚗 Multi-URL Vehicle Inventory Scraper")
    
    if not is_selenium_available():
        st.error("❌ Selenium not installed!")
        st.code("pip install selenium webdriver-manager")
        return
    
    st.markdown("""
    **Extracts ALL fields from MULTIPLE dealer URLs:** URL (Clickable), Source Dealer, VIN, Stock#, Year, Make, Model, Trim, **Condition (New/Used)**, Price, Mileage, 
    Transmission, Drivetrain, Body Style, Ext/Int Color, Engine, Cylinders, Fuel Type, Doors, Passengers
    """)
    
    # Custom CSS for better table display
    st.markdown("""
    <style>
    .vehicle-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
    }
    .vehicle-table th {
        background-color: #1f77b4;
        color: white;
        padding: 10px;
        text-align: left;
        position: sticky;
        top: 0;
    }
    .vehicle-table td {
        padding: 8px;
        border-bottom: 1px solid #ddd;
    }
    .vehicle-table a {
        color: #1f77b4;
        text-decoration: none;
        font-weight: bold;
    }
    .vehicle-table a:hover {
        text-decoration: underline;
    }
    .table-container {
        max-height: 600px;
        overflow-y: auto;
        border: 1px solid #ddd;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        max_vehicles = st.slider("Max Vehicles Per URL", 5, 1000, 50, 5)
        
        st.markdown("---")
        st.markdown("### 📋 Fields Extracted")
        st.code("""
✓ URL (Clickable Link)
✓ Source Dealer (NEW!)
✓ VIN
✓ Stock/Inventory #
✓ Year
✓ Make
✓ Model
✓ Trim
✓ Condition (New/Used/CPO)
✓ Price (Current & Was)
✓ Mileage (KM)
✓ Transmission
✓ Drivetrain
✓ Body Style
✓ Exterior Color
✓ Interior Color
✓ Engine
✓ Cylinders
✓ Fuel Type
✓ Doors
✓ Passengers
✓ Certified Status
✓ Carfax URL
✓ Image URL
""")
    
    # URL Input - MULTIPLE URLS
    st.subheader("🔗 Enter Multiple Dealer Inventory URLs")
    st.markdown("**Enter one URL per line:**")
    
    url_input = st.text_area(
        "Dealer URLs",
        value="""https://www.duboisetfreres.com/en/used-inventory
https://www.duboisetfreres.com/en/new-inventory""",
        height=150,
        placeholder="https://www.dealer1.com/en/used-inventory\nhttps://www.dealer2.com/en/new-inventory\nhttps://www.dealer3.com/en/certified-inventory"
    )
    
    # Parse and show URLs
    urls = parse_urls(url_input)
    
    if urls:
        st.info(f"📋 **{len(urls)} URLs detected:**")
        for i, url in enumerate(urls, 1):
            dealer = get_dealer_name(url)
            st.markdown(f"  {i}. **{dealer}** - `{url[:60]}...`" if len(url) > 60 else f"  {i}. **{dealer}** - `{url}`")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        scrape_btn = st.button("🔍 Scrape All URLs", type="primary", use_container_width=True)
    
    if scrape_btn and urls:
        status = st.empty()
        progress = st.progress(0)
        
        def update(msg, pct=None):
            status.text(msg)
            if pct:
                progress.progress(pct)
        
        def show_warning(msg):
            st.warning(msg)
        
        def show_error(msg):
            st.error(msg)
        
        with st.spinner(f"Scraping {len(urls)} dealer(s)... This may take several minutes."):
            vehicles = scrape_all_vehicles_multi(
                urls, 
                max_vehicles, 
                progress_callback=update,
                warning_callback=show_warning,
                error_callback=show_error
            )
        
        status.empty()
        progress.empty()
        
        if vehicles:
            df = pd.DataFrame(vehicles)
            # Remove completely empty columns
            df = df.loc[:, (df != "").any(axis=0) & df.notna().any(axis=0)]
            st.session_state['df'] = df
            st.success(f"✅ Successfully scraped {len(vehicles)} vehicles from {len(urls)} dealer(s)!")
        else:
            st.error("❌ No vehicles scraped. Check the URLs.")
    
    # Display Results
    if 'df' in st.session_state:
        df = st.session_state['df']
        
        st.markdown("---")
        st.header(f"📊 Results ({len(df)} vehicles)")
        
        # Dealer breakdown
        if 'source_dealer' in df.columns:
            dealer_counts = df['source_dealer'].value_counts()
            if len(dealer_counts) > 0:
                st.markdown("**🏪 Vehicles by Dealer:**")
                dealer_cols = st.columns(min(len(dealer_counts), 4))
                for i, (dealer, count) in enumerate(dealer_counts.items()):
                    if dealer:
                        dealer_cols[i % 4].metric(dealer, count)
        
        # Stats Row 1
        cols = st.columns(6)
        stats = [
            ("Total", len(df)),
            ("URLs", (df.get('url', pd.Series([''])) != "").sum()),
            ("VINs", (df.get('vin', pd.Series([''])) != "").sum()),
            ("Conditions", (df.get('condition', pd.Series([''])) != "").sum()),
            ("Prices", (df.get('price', pd.Series([''])) != "").sum()),
            ("Carfax", (df.get('carfax_url', pd.Series([''])) != "").sum()),
        ]
        for col, (label, value) in zip(cols, stats):
            col.metric(label, value)
        
        # Stats Row 2
        cols2 = st.columns(6)
        stats2 = [
            ("Mileages", (df.get('mileage_km', pd.Series([''])) != "").sum()),
            ("Years", (df.get('year', pd.Series([''])) != "").sum()),
            ("Makes", (df.get('make', pd.Series([''])) != "").sum()),
            ("Models", (df.get('model', pd.Series([''])) != "").sum()),
            ("Trans", (df.get('transmission', pd.Series([''])) != "").sum()),
            ("Colors", (df.get('ext_color', pd.Series([''])) != "").sum()),
        ]
        for col, (label, value) in zip(cols2, stats2):
            col.metric(label, value)
        
        # Condition breakdown
        if 'condition' in df.columns:
            condition_counts = df['condition'].value_counts()
            if len(condition_counts) > 0:
                st.markdown("**Condition Breakdown:**")
                cond_cols = st.columns(len(condition_counts))
                for i, (cond, count) in enumerate(condition_counts.items()):
                    if cond:
                        cond_cols[i].metric(cond, count)
        
        # Column Selector
        st.subheader("📋 Data Table (Click URL to Open Vehicle Page)")
        all_cols = df.columns.tolist()
        
        # Priority columns order - URL FIRST, SOURCE_DEALER second, CONDITION added
        priority = ['url', 'source_dealer', 'condition', 'vin', 'stock_number', 'year', 'make', 'model', 'trim', 'price', 
                   'mileage_km', 'transmission', 'drivetrain', 'body_style', 
                   'ext_color', 'int_color', 'engine', 'cylinders', 'fuel_type', 
                   'doors', 'passengers', 'certified', 'carfax_url']
        default_cols = [c for c in priority if c in all_cols][:12]
        
        selected_cols = st.multiselect(
            "Select columns to display",
            options=all_cols,
            default=default_cols
        )
        
        if selected_cols:
            display_df = df[selected_cols].copy()
        else:
            display_df = df.copy()
        
        # Make URLs clickable
        if 'url' in display_df.columns:
            display_df['url'] = display_df['url'].apply(
                lambda x: f'<a href="{x}" target="_blank">🔗 Open Car</a>' if x else ''
            )
        
        # Make Carfax URLs clickable
        if 'carfax_url' in display_df.columns:
            display_df['carfax_url'] = display_df['carfax_url'].apply(
                lambda x: f'<a href="{x}" target="_blank">📋 Carfax</a>' if x else ''
            )
        
        # Display as HTML table with clickable links
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        html_table = display_df.to_html(escape=False, index=False, classes='vehicle-table')
        st.markdown(html_table, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Also show as regular dataframe for sorting/filtering
        with st.expander("📊 Interactive Table (for sorting/filtering - URLs not clickable)"):
            if selected_cols:
                st.dataframe(df[selected_cols], use_container_width=True, height=400)
            else:
                st.dataframe(df, use_container_width=True, height=400)
        
        # Filter by Dealer
        if 'source_dealer' in df.columns:
            dealers = df['source_dealer'].unique().tolist()
            if len(dealers) > 1:
                with st.expander("🔍 Filter by Dealer"):
                    selected_dealer = st.selectbox("Select Dealer", ["All"] + dealers)
                    if selected_dealer != "All":
                        filtered_df = df[df['source_dealer'] == selected_dealer]
                        st.dataframe(filtered_df, use_container_width=True, height=300)
        
        # Sample Preview with clickable URLs
        with st.expander("👁️ Sample Data Preview (First 3 vehicles)"):
            for i, row in df.head(3).iterrows():
                st.markdown(f"### Vehicle {i+1}")
                
                # Show dealer and URL prominently
                if row.get('source_dealer'):
                    st.markdown(f"**🏪 Dealer:** {row['source_dealer']}")
                if row.get('url'):
                    st.markdown(f"**🔗 Direct Link:** [{row['url'][:60]}...]({row['url']})")
                
                # Show condition badge
                if row.get('condition'):
                    condition = row['condition']
                    if condition == 'New':
                        st.markdown(f"**🏷️ Condition:** 🟢 {condition}")
                    elif condition == 'Used':
                        st.markdown(f"**🏷️ Condition:** 🟡 {condition}")
                    else:
                        st.markdown(f"**🏷️ Condition:** 🔵 {condition}")
                
                cols = st.columns(4)
                items = [(k, v) for k, v in row.items() if v and str(v).strip() and k not in ['url', 'condition', 'source_dealer']]
                for j, (k, v) in enumerate(items):
                    cols[j % 4].write(f"**{k}:** {v}")
                st.markdown("---")
        
        # Quick Links Section
        st.subheader("🔗 Quick Links to All Vehicles")
        with st.expander("Click to expand all vehicle links"):
            current_dealer = None
            for i, row in df.iterrows():
                # Show dealer header when it changes
                if row.get('source_dealer') != current_dealer:
                    current_dealer = row.get('source_dealer')
                    st.markdown(f"### 🏪 {current_dealer}")
                
                if row.get('url'):
                    title = f"{row.get('year', '')} {row.get('make', '')} {row.get('model', '')}".strip()
                    condition_display = f" [{row.get('condition', '')}]" if row.get('condition') else ""
                    vin_display = f" | VIN: {row.get('vin', 'N/A')}" if row.get('vin') else ""
                    price_display = f" | ${row.get('price', 'N/A')}" if row.get('price') else ""
                    st.markdown(f"- [{title or 'Vehicle'}{condition_display}{vin_display}{price_display}]({row['url']})")
        
        # Export
        st.subheader("📥 Download Data")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "⬇️ Download CSV",
                data=csv,
                file_name="vehicle_inventory_multi.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            json_str = df.to_json(orient='records', indent=2)
            st.download_button(
                "⬇️ Download JSON",
                data=json_str,
                file_name="vehicle_inventory_multi.json",
                mime="application/json",
                use_container_width=True
            )
        
        with col3:
            try:
                buffer = BytesIO()
                df.to_excel(buffer, index=False, engine='openpyxl')
                st.download_button(
                    "⬇️ Download Excel",
                    data=buffer.getvalue(),
                    file_name="vehicle_inventory_multi.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except ImportError:
                st.info("Install openpyxl: `pip install openpyxl`")


if __name__ == "__main__":
    main()
