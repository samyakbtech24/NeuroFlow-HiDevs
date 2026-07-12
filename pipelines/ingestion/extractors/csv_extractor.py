import io
import logging
from typing import List
import pandas as pd

from pipelines.ingestion.extractors.extracted_page import ExtractedPage

logger = logging.getLogger("csv-extractor")

def _df_to_markdown_table(df: pd.DataFrame) -> str:
    """
    Manually converts a pandas DataFrame into a Markdown table string.
    Avoids requiring third-party libraries like tabulate.
    """
    if df.empty:
        return ""
        
    columns = list(df.columns)
    col_count = len(columns)
    lines = []
    
    # 1. Header
    lines.append("| " + " | ".join(str(c) for c in columns) + " |")
    # 2. Separator
    lines.append("| " + " | ".join(["---"] * col_count) + " |")
    # 3. Data Rows
    for _, row in df.iterrows():
        cleaned_cells = []
        for cell in row:
            val = str(cell or "").replace("\n", " ").replace("|", "\\|").strip()
            cleaned_cells.append(val)
        lines.append("| " + " | ".join(cleaned_cells) + " |")
        
    return "\n".join(lines)

def extract_csv(file_bytes: bytes) -> List[ExtractedPage]:
    """
    Extracts structured content from CSV bytes.
    - Uses pandas to parse the CSV.
    - Small CSVs (<1000 rows): represented as markdown tables.
    - Large CSVs (>=1000 rows): represented as statistical summaries and sample rows.
    - Slices rows into blocks of 100 rows per ExtractedPage.
    """
    extracted_pages = []
    
    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as e:
        logger.error(f"Failed to read CSV with pandas: {e}")
        return []

    total_rows = len(df)
    page_num = 1

    # 1. If large CSV, prepend a statistical summary page
    if total_rows >= 1000:
        summary_lines = [
            f"CSV Statistical Summary (Total Rows: {total_rows}, Total Columns: {len(df.columns)})",
            "============================================================"
        ]
        
        # Detect column types
        for col in df.columns:
            dtype = str(df[col].dtype)
            summary_lines.append(f"\nColumn: '{col}' (Type: {dtype})")
            
            # Numeric columns stats
            if pd.api.types.is_numeric_dtype(df[col]):
                min_val = df[col].min()
                max_val = df[col].max()
                mean_val = df[col].mean()
                summary_lines.append(f"  - Numeric stats: Min={min_val}, Max={max_val}, Mean={mean_val:.4f}")
            # Categorical columns stats (top-5 value counts)
            else:
                top5 = df[col].value_counts().head(5)
                summary_lines.append("  - Top 5 Value Counts:")
                for val, count in top5.items():
                    summary_lines.append(f"    * {val}: {count}")
        
        # Include first 5 sample rows
        summary_lines.append("\nSample Rows (First 5):")
        summary_lines.append(_df_to_markdown_table(df.head(5)))
        
        extracted_pages.append(ExtractedPage(
            page_number=page_num,
            content="\n".join(summary_lines),
            content_type="text",
            metadata={"type": "summary", "total_rows": total_rows}
        ))
        page_num += 1

    # 2. Slice the dataframe into 100-row blocks
    block_size = 100
    for i in range(0, total_rows, block_size):
        chunk_df = df.iloc[i : i + block_size]
        markdown_chunk = _df_to_markdown_table(chunk_df)
        
        if markdown_chunk.strip():
            extracted_pages.append(ExtractedPage(
                page_number=page_num,
                content=markdown_chunk,
                content_type="table",
                metadata={
                    "page_number": page_num,
                    "row_start": i,
                    "row_end": min(total_rows, i + block_size) - 1,
                    "total_rows": total_rows
                }
            ))
            page_num += 1

    return extracted_pages
