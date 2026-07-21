#!/bin/bash
SRC="/Users/tx/market-data/market.duckdb"
DEST_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/MIS-Backups"
DATE=$(date +%Y-%m-%d)

mkdir -p "$DEST_DIR"
cp "$SRC" "$DEST_DIR/market_$DATE.duckdb"
echo "[$DATE] 备份完成：$DEST_DIR/market_$DATE.duckdb"

cd "$DEST_DIR" || exit
ls -t market_*.duckdb | tail -n +9 | xargs -I {} rm -- {}
echo "当前保留的备份："
ls -la "$DEST_DIR"