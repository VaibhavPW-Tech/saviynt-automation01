import re
import streamlit as st
import pandas as pd

# =========================================
#  Page config & basic styling
# =========================================
st.set_page_config(
    page_title="SOX Access Comparison Tool",
    page_icon="✅",
    layout="wide"
)

st.markdown(
    """
    <style>
    .main {
        background-color: #0b1120;
        color: #e5e7eb;
    }
    .report-box {
        background-color: #020617;
        padding: 1.2rem 1.5rem;
        border-radius: 0.5rem;
        border: 1px solid #1f2937;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.6);
    }
    .stButton>button {
        border-radius: 0.4rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("SOX Access Comparison Tool")
st.caption("Upload the Analytics Summary and Dump files, run checks, and see per‑check summaries.")

# =========================================
#  Helper functions
# =========================================
def make_unique(cols):
    """Make column names unique (for Streamlit/pyarrow display)."""
    seen = {}
    new_cols = []
    for c in cols:
        if c not in seen:
            seen[c] = 0
            new_cols.append(c)
        else:
            seen[c] += 1
            new_cols.append(f"{c}_{seen[c]}")
    return new_cols


def extract_id_from_username(username: str) -> str:
    """
    Extract ID from a string like 'Name (12345)' => '12345'.
    Returns upper-stripped string or '' if not found.
    """
    if pd.isna(username):
        return ""
    text = str(username)
    match = re.search(r"\(([^)]+)\)", text)
    if match:
        return match.group(1).strip().upper()
    return ""


# =========================================
#  1. File upload (both files used in all checks)
# =========================================
st.header("Upload Files")

col_up1, col_up2 = st.columns(2)

with col_up1:
    analytics_file = st.file_uploader(
        "Upload Saviynt Summary file (e.g. Analytics_Summary_*.xlsx)",
        type=["xlsx"],
        key="analytics"
    )

with col_up2:
    sbl_file = st.file_uploader(
        "Upload Dump Automated file (e.g. sbl_am_automated.xlsx)",
        type=["xlsx"],
        key="sbl"
    )

df_analytics, df_sbl = None, None

if analytics_file is not None:
    df_analytics = pd.read_excel(analytics_file)

if sbl_file is not None:
    df_sbl = pd.read_excel(sbl_file)

# Extra safety: stop execution until both are uploaded
if df_analytics is None or df_sbl is None:
    st.info("Please upload both files to continue.")
    st.stop()

# Row counts summary (now guaranteed not None)
analytics_rows = len(df_analytics)
sbl_rows = len(df_sbl)
st.success(
    f"Files uploaded successfully. "
    f"Saviynt file has {analytics_rows} rows. "
    f"Dump Automated file has {sbl_rows} rows."
)

all_results = []  # collect partial results from all checks

# =========================================
#  2. Check 1 – Date comparisons (Mode A & Mode B)
# =========================================
st.header("Check 1 – Access is provisioned post approvals only")

check1_mode = st.radio(
    "Choose Check 1 mode:",
    options=[
        "A: Approval vs Task Completion (Saviynt only)",
        "B: Application Created Date vs Saviynt Request Approved Date (Unique by SSO)"
    ],
    index=0,
    key="check1_mode"
)

# ----------------- MODE A: Existing logic -----------------
if check1_mode.startswith("A"):
    with st.expander("Configure Check 1 (Mode A)", expanded=True):
        c1_1, c1_2, c1_3 = st.columns(3)

        with c1_1:
            approval_col = st.selectbox(
                "Approval Date column (Analytics)",
                options=df_analytics.columns,
                key="approval_date_col"
            )

        with c1_2:
            completion_col = st.selectbox(
                "Task Completion Date column (Analytics)",
                options=df_analytics.columns,
                key="completion_date_col"
            )

        with c1_3:
            key_col_1 = st.selectbox(
                "Key/ID column (Analytics, for report)",
                options=df_analytics.columns,
                key="key_col_1"
            )

        run_check1 = st.checkbox("Run Check 1 (Mode A, ALL rows)", value=True, key="run_check1A")

    if run_check1:
        df_check1 = df_analytics.copy()

        df_check1["_approval_datetime"] = pd.to_datetime(df_check1[approval_col], errors="coerce")
        df_check1["_completion_datetime"] = pd.to_datetime(df_check1[completion_col], errors="coerce")

        def check_approval_before_completion(row):
            a = row["_approval_datetime"]
            c = row["_completion_datetime"]
            if pd.isna(a) or pd.isna(c):
                return "Failed - Missing date"
            return "Yes" if a <= c else "Failed - Approval after completion"

        df_check1["Check1_Result"] = df_check1.apply(check_approval_before_completion, axis=1)
        df_check1["Check1_Reason"] = df_check1["Check1_Result"]

        all_results.append(df_check1[[key_col_1, "Check1_Result", "Check1_Reason"]])

        total_rows_c1 = len(df_check1)
        failed_rows_c1 = df_check1[df_check1["Check1_Result"].str.startswith("Failed")]
        passed_rows_c1 = total_rows_c1 - len(failed_rows_c1)

        st.subheader("Check 1 (Mode A) Summary")
        st.write(f"Total rows evaluated: {total_rows_c1}")
        st.write(f"Passed: {passed_rows_c1}")
        st.write(f"Failed: {len(failed_rows_c1)}")

        if len(failed_rows_c1) > 0:
            st.write("Failed rows for Check 1 (Mode A):")
            failed_view = failed_rows_c1[[key_col_1, approval_col, completion_col, "Check1_Result"]].copy()
            failed_view.columns = make_unique(failed_view.columns)
            st.dataframe(failed_view)
        else:
            st.success("There were no issues or failed cases for this check (Mode A).")

        st.write("Full Check 1 (Mode A) results (ALL rows):")
        preview_cols = [key_col_1, approval_col, completion_col, "Check1_Result"]
        preview = df_check1[preview_cols].copy()
        preview.columns = make_unique(preview.columns)
        st.dataframe(preview)

# ----------------- MODE B: SBL Created Date vs Analytics Request Approved Date -----------------
else:
    with st.expander("Configure Check 1 (Mode B)", expanded=True):
        c1b_1, c1b_2, c1b_3, c1b_4 = st.columns(4)

        with c1b_1:
            sbl_sso_col = st.selectbox(
                "User SSO / ID column in Dump (Application file)",
                options=df_sbl.columns,
                key="sbl_sso_col_c1"
            )

        with c1b_2:
            sbl_created_date_col = st.selectbox(
                "Created Date column in Dump (Application file)",
                options=df_sbl.columns,
                key="sbl_created_date_col_c1"
            )

        with c1b_3:
            analytics_sso_col = st.selectbox(
                "User SSO / ID column in Saviynt file",
                options=df_analytics.columns,
                key="analytics_sso_col_c1"
            )

        with c1b_4:
            analytics_approved_date_col = st.selectbox(
                "Request Approved Date column in Saviynt file",
                options=df_analytics.columns,
                key="analytics_approved_date_col_c1"
            )

        key_col_1b = st.selectbox(
            "Key/ID column (Saviynt, for report)",
            options=df_analytics.columns,
            key="key_col_1b"
        )

        username_is_pure_id_c1 = st.checkbox(
            "Saviynt SSO column already contains pure ID (no brackets)",
            value=True,
            key="username_is_pure_id_c1",
            help="Tick if the selected Saviynt user column is just the ID (e.g., 223055402), not 'Name (223055402)'."
        )

        run_check1B = st.checkbox(
            "Run Check 1 (Mode B, ALL rows)",
            value=True,
            key="run_check1B"
        )

    if run_check1B:
        # --- Normalize SSO/ID in SBL (Dump) ---
        sbl_tmp = df_sbl[[sbl_sso_col, sbl_created_date_col]].copy()

        # Ensure SSO column is a Series
        sso_series = sbl_tmp[sbl_sso_col]
        if isinstance(sso_series, pd.DataFrame):
            sso_series = sso_series.iloc[:, 0]

        sbl_tmp["_sso_norm"] = sso_series.astype(str).str.strip().str.upper()

        # Ensure created-date column is a Series
        created_series = sbl_tmp[sbl_created_date_col]
        if isinstance(created_series, pd.DataFrame):
            created_series = created_series.iloc[:, 0]

        # Convert created date to date (no time)
        sbl_tmp["_created_dt"] = pd.to_datetime(created_series, errors="coerce").dt.date

        # Map: SSO -> earliest created date (if multiple rows in SBL)
        sbl_created_map = (
            sbl_tmp.groupby("_sso_norm")["_created_dt"]
            .min()
            .to_dict()
        )

        # --- Normalize SSO/ID in Analytics ---
        df_check1B = df_analytics[[analytics_sso_col, analytics_approved_date_col, key_col_1b]].copy()

        analytics_user_series = df_check1B[analytics_sso_col]
        if isinstance(analytics_user_series, pd.DataFrame):
            analytics_user_series = analytics_user_series.iloc[:, 0]

        if username_is_pure_id_c1:
            df_check1B["_sso_norm"] = analytics_user_series.astype(str).str.strip().str.upper()
        else:
            df_check1B["_sso_norm"] = analytics_user_series.apply(extract_id_from_username)

        # Ensure approved-date column is a Series
        approved_series = df_check1B[analytics_approved_date_col]
        if isinstance(approved_series, pd.DataFrame):
            approved_series = approved_series.iloc[:, 0]

        # Convert approved date to date (no time)
        df_check1B["_approved_dt"] = pd.to_datetime(approved_series, errors="coerce").dt.date

        # --- Row-wise comparison: Approved Date vs Created Date ---
        def compare_approved_vs_created(row):
            sso = row["_sso_norm"]
            approved_dt = row["_approved_dt"]

            # If we can't extract any SSO at all from Analytics -> fail
            if not sso:
                return "Failed - No SSO/ID extracted", None, ""

            created_dt = sbl_created_map.get(sso, None)

            # If SSO not found in SBL -> fail
            if created_dt is None:
                return "Failed - SSO/ID not found in Application File", None, sso

            # If created date exists in mapping but is NaN -> fail
            if pd.isna(created_dt):
                return "Failed - Created date missing in Application File", None, sso

            # From this point, we HAVE a created date in SBL
            if pd.isna(approved_dt):
                return "Failed - Approved date missing in Saviynt File", created_dt, sso

            # Rule: Approved date must be <= Created date
            if approved_dt <= created_dt:
                return "Yes", created_dt, sso
            else:
                return "Failed - Approved date is after created date", created_dt, sso

        results_b = df_check1B.apply(
            lambda r: compare_approved_vs_created(r),
            axis=1,
            result_type="expand"
        )

        df_check1B["Check1_Result"] = results_b[0]
        df_check1B["Created Date"] = results_b[1]
        df_check1B["SSO ID"] = results_b[2]
        df_check1B["Approved Date"] = df_check1B["_approved_dt"]
        df_check1B["Check1_Reason"] = df_check1B["Check1_Result"]

        # --- Collect for final download / combined results ---
        all_results.append(
            df_check1B[
                [
                    key_col_1b,
                    "SSO ID",
                    "Created Date",
                    "Approved Date",
                    "Check1_Result",
                    "Check1_Reason",
                ]
            ]
        )

        total_rows_c1b = len(df_check1B)
        failed_rows_c1b = df_check1B[df_check1B["Check1_Result"].str.startswith("Failed")]
        passed_rows_c1b = total_rows_c1b - len(failed_rows_c1b)

        st.subheader("Check 1 (Mode B) Summary")
        st.write(f"Total rows evaluated (Analytics): {total_rows_c1b}")
        st.write(f"Passed: {passed_rows_c1b}")
        st.write(f"Failed: {len(failed_rows_c1b)}")

        if len(failed_rows_c1b) > 0:
            st.write("Failed rows for Check 1 (Mode B):")
            failed_view_b = failed_rows_c1b[
                [
                    key_col_1b,
                    analytics_sso_col,
                    "SSO ID",
                    "Created Date",
                    "Approved Date",
                    "Check1_Result",
                ]
            ].copy()
            failed_view_b.columns = make_unique(failed_view_b.columns)
            st.dataframe(failed_view_b)
        else:
            st.success("There were no issues or failed cases for this check (Mode B).")

        st.write("Full Check 1 (Mode B) results (ALL rows):")
        preview_cols_b = [
            key_col_1b,
            analytics_sso_col,
            "SSO ID",
            "Created Date",
            "Approved Date",
            "Check1_Result",
        ]
        preview_b = df_check1B[preview_cols_b].copy()
        preview_b.columns = make_unique(preview_b.columns)
        st.dataframe(preview_b)

# =========================================
#  3. Check 2 – SOD: Inter-check between Requested / Approvals / Granted
# =========================================
st.header("Check 2 – SOD: Requested vs Approvals vs Granted")

with st.expander("Configure Check 2", expanded=True):
    st.markdown("**Approval levels (up to 5, Leave unused ones blank ).**")
    c2_cols = st.columns(5)
    approval_cols = []

    for i, col in enumerate(c2_cols, start=1):
        with col:
            selected = st.selectbox(
                f"Approval Level {i} column (optional)",
                options=[""] + list(df_analytics.columns),
                key=f"appr_level_{i}"
            )
            approval_cols.append(selected if selected != "" else None)

    requested_by_col = st.selectbox(
        "Requested By column (Analytics)",
        options=df_analytics.columns,
        key="requested_by_col"
    )

    # NEW: format of Requested For
    requested_is_pure_id = st.checkbox(
        "Requested By already contains pure ID (no Name(ID) format)",
        value=True,
        key="requested_is_pure_id_c2",
        help="Tick if Requested By is just the ID (e.g. 223055402), not 'Name (223055402)'."
    )

    st.markdown("**Granted By source (choose one option):**")
    c2_g1, c2_g2 = st.columns(2)
    with c2_g1:
        granted_by_col = st.selectbox(
            "Granted By column (optional)",
            options=[""] + list(df_analytics.columns),
            key="granted_by_col"
        )
    with c2_g2:
        granted_by_id_input = st.text_input(
            "OR enter a single Granted By ID (applies to all rows)",
            value="",
            key="granted_by_id_input"
        )

    # Format of approval & granted columns
    values_are_name_id = st.checkbox(
        "Approval/Granted columns use 'Name (ID)' format (e.g. John Smith (12345))",
        value=True,
        key="values_are_name_id_c2",
        help="If ticked, the tool will extract the ID inside brackets and compare only IDs."
    )

    key_col_2 = st.selectbox(
        "Key/ID column (Analytics, for report)",
        options=df_analytics.columns,
        key="key_col_2"
    )

    run_check2 = st.checkbox("Run Check 2 (for ALL rows)", value=True)

if run_check2:
    df_check2 = df_analytics.copy()

    # ---------- Normalization helper (to ID) ----------
    def normalize_id(val, treat_as_name_id: bool):
        """
        Convert a cell value to a comparable ID.
        - If NaN/blank -> "" (ignored in comparisons).
        - If treat_as_name_id=True -> extract 'ID' from 'Name (ID)'.
        - Else -> just strip & uppercase.
        """
        if pd.isna(val):
            return ""
        text = str(val).strip()
        if text == "":
            return ""
        if treat_as_name_id:
            # Your helper: Name (12345) -> 12345 (upper-stripped or "")
            return extract_id_from_username(text)
        else:
            return text.upper()

    # ---------- Requested By (ID) ----------
    rb_series = df_check2[requested_by_col]
    if isinstance(rb_series, pd.DataFrame):
        rb_series = rb_series.iloc[:, 0]
    df_check2["_requested_id"] = rb_series.apply(
        lambda v: normalize_id(v, treat_as_name_id=not requested_is_pure_id)
    )

    # ---------- Granted By source ----------
    granted_by_col_selected = granted_by_col if granted_by_col != "" else None

    # manual ID (same for all rows, if provided)
    granted_by_id_manual = granted_by_id_input.strip()
    granted_by_id_manual_norm = (
        normalize_id(granted_by_id_manual, treat_as_name_id=False)
        if granted_by_id_manual
        else ""
    )

    if granted_by_col_selected:
        gb_series = df_check2[granted_by_col_selected]
        if isinstance(gb_series, pd.DataFrame):
            gb_series = gb_series.iloc[:, 0]
        df_check2["_granted_id_col"] = gb_series.apply(
            lambda v: normalize_id(v, treat_as_name_id=values_are_name_id)
        )
    else:
        df_check2["_granted_id_col"] = ""  # will be ignored if manual ID used

    # final granted ID used per row:
    # priority: manual ID (if entered) else column value
    df_check2["_granted_id"] = df_check2.apply(
        lambda r: granted_by_id_manual_norm if granted_by_id_manual_norm else r["_granted_id_col"],
        axis=1,
    )

    # ---------- Approvals (ID) ----------
    norm_approval_cols = []  # list of (original_col_name, normalized_col_name)
    for idx, col_name in enumerate(approval_cols, start=1):
        if col_name is None:
            continue
        series = df_check2[col_name]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        norm_name = f"_appr_{idx}_id"
        df_check2[norm_name] = series.apply(
            lambda v: normalize_id(v, treat_as_name_id=values_are_name_id)
        )
        norm_approval_cols.append((col_name, norm_name))

    # ---------- Row-wise SoD check (by ID) ----------
    def sod_intercheck(row):
        req_id = row["_requested_id"]
        grn_id = row["_granted_id"]

        conflicts = []

        # Requested vs Granted
        if req_id and grn_id and req_id == grn_id:
            conflicts.append("Requested ID = Granted ID")

        # Approvals vs Requested / Granted
        for orig_col, norm_col in norm_approval_cols:
            appr_id = row[norm_col]
            if not appr_id:
                continue  # allow blanks

            if req_id and appr_id == req_id:
                conflicts.append(f"Approval ({orig_col}) ID = Requested ID")
            if grn_id and appr_id == grn_id:
                conflicts.append(f"Approval ({orig_col}) ID = Granted ID")

        if not conflicts:
            return "Yes", ""

        reason = "Failed - SoD conflict: " + "; ".join(conflicts)
        return reason, "; ".join(conflicts)

    results = df_check2.apply(sod_intercheck, axis=1, result_type="expand")
    df_check2["Check2_Result"] = results[0]
    df_check2["Check2_Conflicts"] = results[1]
    df_check2["Check2_Reason"] = df_check2["Check2_Result"]

    # ---------- Columns to output ----------
    cols_for_output = [key_col_2, requested_by_col]
    if granted_by_col_selected:
        cols_for_output.append(granted_by_col_selected)
    for orig_col, _norm_col in norm_approval_cols:
        cols_for_output.append(orig_col)

    # show normalized IDs for transparency
    cols_for_output.append("_requested_id")
    cols_for_output.append("_granted_id")
    for _, norm_col in norm_approval_cols:
        cols_for_output.append(norm_col)

    cols_for_output += ["Check2_Result", "Check2_Reason", "Check2_Conflicts"]

    all_results.append(df_check2[cols_for_output])

    total_rows_c2 = len(df_check2)
    failed_rows_c2 = df_check2[df_check2["Check2_Result"].str.startswith("Failed")]
    passed_rows_c2 = total_rows_c2 - len(failed_rows_c2)

    st.subheader("Check 2 Summary")
    st.write(f"Total rows evaluated: {total_rows_c2}")
    st.write(f"Passed: {passed_rows_c2}")
    st.write(f"Failed: {len(failed_rows_c2)}")

    if len(failed_rows_c2) > 0:
        st.write("Failed rows for Check 2:")
        failed_view2 = failed_rows_c2[cols_for_output].copy()
        failed_view2.columns = make_unique(failed_view2.columns)
        st.dataframe(failed_view2)
    else:
        st.success("There were no issues or failed cases for this check.")

    st.write("Full Check 2 results (ALL rows):")
    preview2 = df_check2[cols_for_output].copy()
    preview2.columns = make_unique(preview2.columns)
    st.dataframe(preview2)

# =========================================
#  4. Check 3 – Role-by-role comparison (multiple roles per user, ALL rows)
# =========================================
st.header("Check 3 – Role Requested = Role Provisioned")

with st.expander("Configure Check 3 (User & Role Comparison)", expanded=True):
    c3_1, c3_2 = st.columns(2)
    c3_3, c3_4 = st.columns(2)

    with c3_1:
        sbl_userid_col = st.selectbox(
            "User ID column in Dump File",
            options=df_sbl.columns.tolist(),
            key="sbl_userid_col"
        )

    with c3_2:
        sbl_role_col = st.selectbox(
            "Role column in Dump File",
            options=df_sbl.columns.tolist(),
            key="sbl_role_col"
        )

    with c3_3:
        analytics_username_col = st.selectbox(
            "User identifier column in Saviynt  (either Name(ID) or pure ID)",
            options=df_analytics.columns.tolist(),
            key="analytics_username_col"
        )

    with c3_4:
        analytics_role_col = st.selectbox(
            "Role column in Saviynt",
            options=df_analytics.columns.tolist(),
            key="analytics_role_col"
        )

    key_col_3 = st.selectbox(
        "Key/ID column for reporting (from Saviynt Summary)",
        options=df_analytics.columns.tolist(),
        key="key_col_3"
    )

    username_is_pure_id = st.checkbox(
        "Saviynt user column already contains pure ID (no brackets)",
        value=True,
        help="Tick this if the selected Analytics user column is just the ID (e.g., 223055402), "
             "not 'Name (223055402)'."
    )

    run_check3 = st.checkbox("Run Check 3 (uses ALL rows in both files)", value=True)

if run_check3:
    # ---------- Build SBL map: ID -> set of roles ----------
    sbl_id_role = df_sbl[[sbl_userid_col, sbl_role_col]].copy()

    col_user = sbl_id_role[sbl_userid_col]
    if isinstance(col_user, pd.DataFrame):
        col_user = col_user.iloc[:, 0]

    col_role = sbl_id_role[sbl_role_col]
    if isinstance(col_role, pd.DataFrame):
        col_role = col_role.iloc[:, 0]

    sbl_id_role["_user_id"] = col_user.astype(str).str.strip().str.upper()
    sbl_id_role["_role_norm"] = col_role.astype(str).str.strip().str.upper()

    sbl_map = (
        sbl_id_role.groupby("_user_id")["_role_norm"]
        .apply(lambda x: set(r for r in x if r))
        .to_dict()
    )

    # ---------- Apply to ALL rows in Analytics ----------
    df_check3 = df_analytics[[analytics_username_col, analytics_role_col, key_col_3]].copy()

    # Ensure we are working with Series for username and role
    user_col_series = df_check3[analytics_username_col]
    if isinstance(user_col_series, pd.DataFrame):
        user_col_series = user_col_series.iloc[:, 0]

    role_col_series = df_check3[analytics_role_col]
    if isinstance(role_col_series, pd.DataFrame):
        role_col_series = role_col_series.iloc[:, 0]

    if username_is_pure_id:
        df_check3["_user_id"] = user_col_series.astype(str).str.strip().str.upper()
    else:
        df_check3["_user_id"] = user_col_series.apply(extract_id_from_username)

    df_check3["_role_norm"] = role_col_series.astype(str).str.strip().str.upper()

    def compare_row(row):
        uid = row["_user_id"]
        role = row["_role_norm"]

        if not uid:
            return "Failed - No ID extracted from username"

        roles_in_sbl = sbl_map.get(uid, None)
        if roles_in_sbl is None or len(roles_in_sbl) == 0:
            return "Failed - User ID not found in Application File"

        # Role-by-role comparison (multiple roles per user allowed)
        if role in roles_in_sbl:
            return "Yes"
        else:
            return "Failed - Role not found for this ID in Application File"

    df_check3["Check3_Result"] = df_check3.apply(compare_row, axis=1)
    df_check3["Check3_Reason"] = df_check3["Check3_Result"]

    all_results.append(
        df_check3[[key_col_3, "_user_id", analytics_role_col, "Check3_Result", "Check3_Reason"]]
    )

    # ---------- Summaries and full views ----------
    total_rows_c3 = len(df_check3)
    failed_rows_c3 = df_check3[df_check3["Check3_Result"].str.startswith("Failed")]
    passed_rows_c3 = df_check3[df_check3["Check3_Result"] == "Yes"]

    st.subheader("Check 3 Summary")
    st.write(f"Total rows evaluated (Analytics): {total_rows_c3}")
    st.write(f"Passed: {len(passed_rows_c3)}")
    st.write(f"Failed: {len(failed_rows_c3)}")

    st.write("Failed rows for Check 3 (ALL):")
    if not failed_rows_c3.empty:
        failed_view3 = failed_rows_c3[
            [key_col_3, analytics_username_col, "_user_id", analytics_role_col, "Check3_Result"]
        ].copy()
        failed_view3.columns = make_unique(failed_view3.columns)
        st.dataframe(failed_view3)
    else:
        st.success("There were no failed cases for Check 3.")

    st.write("Passed rows for Check 3 (ALL):")
    if not passed_rows_c3.empty:
        passed_view3 = passed_rows_c3[
            [key_col_3, analytics_username_col, "_user_id", analytics_role_col, "Check3_Result"]
        ].copy()
        passed_view3.columns = make_unique(passed_view3.columns)
        st.dataframe(passed_view3)
    else:
        st.info("There were no passed cases for Check 3.")

    st.write("All rows for Check 3 (ALL):")
    all_view3 = df_check3[
        [key_col_3, analytics_username_col, "_user_id", analytics_role_col, "Check3_Result"]
    ].copy()
    all_view3.columns = make_unique(all_view3.columns)
    st.dataframe(all_view3)
