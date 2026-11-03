
@st.cache_data(ttl=3600)
def get_symbols():
    try:
        # Nifty 500 constituents list
        url = "https://raw.githubusercontent.com/BKKB20/nse-index-history/main/current_members/NIFTY_500.csv"

        df = pd.read_csv(url)

        # Symbol column खोजें
        symbol_col = next(
            (c for c in df.columns if c.strip().lower() == "symbol"),
            None
        )

        if symbol_col is None:
            st.error("Nifty 500 Symbol column नहीं मिली")
            return []

        symbols = (
            df[symbol_col]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        # NSE F&O list
        fo_url = "https://archives.nseindia.com/content/fo/fo_mktlots.csv"
        fo = pd.read_csv(fo_url)

        fo.columns = [str(c).strip() for c in fo.columns]

        fo_col = next(
            (c for c in fo.columns if "SYMBOL" in c.upper()),
            None
        )

        if fo_col:
            fo_symbols = set(
                fo[fo_col].dropna().astype(str).str.strip()
            )

            # F&O शेयर हटाएँ
            symbols = [
                s for s in symbols
                if s not in fo_symbols
            ]

        return sorted(symbols)

    except Exception as e:
        st.error(f"Nifty 500 list error: {e}")
        return []
