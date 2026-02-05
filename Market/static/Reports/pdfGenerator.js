async function loadSVGAsImage(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        // img.crossOrigin = "Anonymous";
        img.src = src;
        img.onload = () => {
            try {
                const canvas = document.createElement("canvas");
                const ctx = canvas.getContext("2d");

                // Larger logo canvas for better resolution
                canvas.width = 600;
                canvas.height = 600;

                ctx.fillStyle = "white";
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

                const dataUrl = canvas.toDataURL("image/png");
                resolve(dataUrl);
            } catch (err) {
                reject(new Error("Failed to convert image to PNG: " + err.message));
            }
        };
        img.onerror = () => reject(new Error("Failed to load image from " + src));
    });
}

// Clean text for PDF
function cleanText(str) {
    if (!str) return "";
    return str
        .replace(/↳/g, "")
        .replace(/&nbsp;/g, " ")
        .replace(/&amp;/g, "&")
        .replace(/&#[0-9]+;/g, " ")
        .replace(/[^\x20-\x7E]/g, "")
        .trim();
}

// Check if a row is a totals row
function isTotalsRow(row) {
    const firstCellText = cleanText(row.querySelector('td:first-child')?.textContent || '').toLowerCase();
    return firstCellText.includes('total') || firstCellText.includes('grand') || firstCellText.includes('sum');
}

// Add this helper function before generatePDF()
function getRowHierarchyLevel(row) {
    // Check for common indentation patterns
    if (row.classList.contains('level-1') || row.classList.contains('child')) return 1;
    if (row.classList.contains('level-2') || row.classList.contains('grandchild')) return 2;
    if (row.classList.contains('level-3') || row.classList.contains('great-grandchild')) return 3;
    
    // Check data attributes
    const level = row.dataset.level || row.dataset.hierarchyLevel;
    if (level) return parseInt(level);
    
    // Check for padding/margin in inline styles
    const style = row.getAttribute('style') || '';
    const paddingMatch = style.match(/padding-left:\s*(\d+)px/);
    if (paddingMatch) {
        const padding = parseInt(paddingMatch[1]);
        return Math.ceil(padding / 20); // Adjust divisor based on your indent size
    }
    
    // Check first cell for visual indentation (arrows, bullets, etc.)
    const firstCell = row.querySelector('td:first-child');
    if (firstCell) {
        const text = firstCell.textContent;
        const arrowCount = (text.match(/↳/g) || []).length;
        if (arrowCount > 0) return arrowCount;
    }
    
    return 0; // Parent level
}

async function generatePDF() {
    if (!window.currentReportType) {
        showLoadingOverlay("No report selected. Please select a report first.");
        setTimeout(hideLoadingOverlay, 2000);
        return;
    }

    showLoadingOverlay("Generating PDF, please wait...");

    const { jsPDF } = window.jspdf;

    const tempTable = document.querySelector("#report-content table");
    if (!tempTable) {
        showLoadingOverlay("No report content available.");
        setTimeout(hideLoadingOverlay, 2000);
        return;
    }

    const headerCells = Array.from(tempTable.querySelectorAll("th"));
    const avgColLengths = headerCells.map((th, i) => {
        const headerLen = th.textContent.trim().length;
        const dataCells = Array.from(tempTable.querySelectorAll(`tbody tr td:nth-child(${i + 1})`));
        const avgDataLen = dataCells.reduce((sum, td) => sum + cleanText(td.textContent).length, 0) / (dataCells.length || 1);
        return Math.max(headerLen, avgDataLen);
    });

    const estimatedTotalTextUnits = avgColLengths.reduce((a, b) => a + b, 0);
    const orientation = estimatedTotalTextUnits > 120 ? "landscape" : "portrait";

    console.log(`📄 Using ${orientation} orientation (est. width units: ${estimatedTotalTextUnits.toFixed(1)})`);

    const doc = new jsPDF({
        orientation,
        unit: "mm",
        format: "a4"
    });

    const pdfContent = document.getElementById("pdfContent");
    const reportContent = document.getElementById("report-content");
    const title = reportContent.querySelector("h1").textContent;
    pdfContent.querySelector("h1").textContent = title;

    // Filters
    const filterList = document.getElementById("filterList");
    filterList.innerHTML = "";
    getActiveFilters().forEach(filter => {
        const li = document.createElement("li");
        li.textContent = filter;
        li.style.fontFamily = "Helvetica, sans-serif";
        li.style.fontSize = "12px";
        filterList.appendChild(li);
    });

    // Table clone
    const table = reportContent.querySelector("table").cloneNode(true);
    table.querySelectorAll("th, td").forEach(cell => {
        cell.style.border = "none";
        cell.style.padding = "6px 8px";
    });

    const visibleRows = Array.from(table.querySelectorAll("tbody tr")).filter(
        row => !row.classList.contains("hidden") && row.style.display !== "none"
    );
    const tbody = table.querySelector("tbody");
    tbody.innerHTML = "";
    visibleRows.forEach(row => tbody.appendChild(row));
    document.getElementById("reportTable").innerHTML = "";
    document.getElementById("reportTable").appendChild(table);

    // Load logo
    let logoDataUrl = null;
    try {
        logoDataUrl = await loadSVGAsImage("/static/Image/LogoAndText.svg");
    } catch (err) {
        console.warn("Logo loading failed:", err);
        logoDataUrl = null;
    }

    try {
        const pageHeight = doc.internal.pageSize.getHeight();
        const pageWidth = doc.internal.pageSize.getWidth();
        const margin = 12;
        const usableWidth = pageWidth - 2 * margin;

        let currentY = margin;

        // Extract headers + data
        const headers = Array.from(table.querySelectorAll("th")).map(th => th.textContent.trim());
        const rows = Array.from(table.querySelectorAll("tbody tr"));
        const tableData = rows.map(row => ({
            data: Array.from(row.querySelectorAll("td")).map(td => cleanText(td.textContent)),
            isTotals: isTotalsRow(row),
            hierarchyLevel: getRowHierarchyLevel(row)
        }));

        // stable line height (mm) used for headers and row height calculations
        const lineHeight = 5;
        
        // Determine column widths
        const colTextLengths = headers.map((header, colIndex) => {
            let total = header.length;
            let count = 1;
            for (const row of tableData) {
                const cellText = cleanText(row.data[colIndex] || "");
                total += cellText.length;
                count++;
            }
            return total / count;
        });

        let colWidths = colTextLengths.map(l => (l / colTextLengths.reduce((a, b) => a + b, 0)) * usableWidth);
        colWidths = colWidths.map(w => Math.max(15, Math.min(w, 60)));
        const adjustedTotal = colWidths.reduce((a, b) => a + b, 0);
        colWidths = colWidths.map(w => (w / adjustedTotal) * usableWidth);

        // Helper: draw page header
        function drawPageHeader(pageTitle, firstPage = false) {
            let y = margin;

            if (logoDataUrl) {
                // smaller logo on subsequent pages
                const logoWidth = firstPage ? 30 : 14;
                const logoHeight = firstPage ? 30 : 14;
                doc.addImage(logoDataUrl, "PNG", (pageWidth - logoWidth) / 2, y, logoWidth, logoHeight);
                y += logoHeight + 5;
            }

            if (firstPage) {
                doc.setFontSize(18);
                doc.setFont("helvetica", "bold");
                doc.text(pageTitle, pageWidth / 2, y, { align: "center" });
                y += 12;

                doc.setFontSize(11);
                doc.setFont("helvetica", "bold");
                if (window.reportParameters.dateCreated) {
                    doc.text(`As On: ${window.reportParameters.dateCreated}`, pageWidth - margin, y, { align: "right" });
                }
                y += 6;

                doc.text("Active Filters:", margin, y);
                if (window.reportParameters.startDate && window.reportParameters.endDate) {
                    const dateLabel = `For The Period: ${window.reportParameters.startDate} to ${window.reportParameters.endDate}`;
                    doc.text(dateLabel, pageWidth - margin, y, { align: "right" });
                }
                y += 6;

                doc.setFont("helvetica", "normal");
                getActiveFilters().forEach(filter => {
                    const textLines = doc.splitTextToSize(`• ${filter}`, usableWidth - 10);
                    doc.text(textLines, margin + 4, y);
                    y += 5 * textLines.length;
                });
                y += 8;
            }

            // Headers: limit to 2 lines, uniform height
            doc.setFontSize(10);
            doc.setFont("helvetica", "bold");

            const allHeaderTextLines = headers.map((header, i) =>
                doc.splitTextToSize(header, colWidths[i] - 2).slice(0, 2)
            );

            // add a small extra padding to avoid bottom-line clipping
            const maxHeaderHeight = Math.max(...allHeaderTextLines.map(lines => lineHeight * lines.length)) + 6;

            headers.forEach((header, i) => {
                const xPos = margin + colWidths.slice(0, i).reduce((sum, w) => sum + w, 0);
                const headerText = allHeaderTextLines[i];

                doc.setFillColor(233, 239, 247);
                doc.rect(xPos, y, colWidths[i], maxHeaderHeight, "F");

                // place text vertically centered with safe padding
                const textY = y + (maxHeaderHeight - (lineHeight * headerText.length)) / 2 + (lineHeight - 0.5);
                doc.text(headerText, xPos + colWidths[i] / 2, textY, { align: "center" });
            });

            return y + maxHeaderHeight + 2;
        }

        currentY = drawPageHeader(title, true);

        // Render rows
        doc.setFontSize(9);
        let rowIndex = 0;
        tableData.forEach(rowInfo => {
            if (currentY > pageHeight - 20) {
                doc.addPage();
                currentY = drawPageHeader(title, false);
            }

            const baseRowHeight = 7;
            const row = rowInfo.data;
            const isTotals = rowInfo.isTotals;
            const hierarchyLevel = rowInfo.hierarchyLevel || 0;
            
            // Indent amount (in mm) - adjust as needed
            const indentPerLevel = 4;
            const totalIndent = hierarchyLevel * indentPerLevel;

            let bgColor, textColor, fontStyle, rowHeight;
            if (isTotals) {
                // Professional dark gray background with white bold text for totals row
                bgColor = [233, 239, 247]; // Professional dark gray background
                textColor = [0, 0, 0]; // White text
                fontStyle = "bold";
                rowHeight = Math.max(baseRowHeight + 2, 9); // Slightly taller for totals row
            } else {
                // Normal alternating colors for regular rows
                bgColor = rowIndex % 2 === 0 ? [245, 247, 250] : [255, 255, 255];
                textColor = [0, 0, 0]; // Black text
                fontStyle = hierarchyLevel > 0 ? "normal" : "normal";
                
                const cellData = row.map((cell, i) => {
                    const text = cleanText(cell || "");
                    const textLines = doc.getTextWidth(text) > colWidths[i] - 4
                        ? doc.splitTextToSize(text, colWidths[i] - 4)
                        : [text];
                    return { textLines, cellHeight: Math.max(baseRowHeight, lineHeight * textLines.length) };
                });
                rowHeight = Math.max(...cellData.map(c => c.cellHeight));
                // add a small padding to prevent bottom line clipping
                rowHeight += 2;
            }

            headers.forEach((_, i) => {
                const baseXPos = margin + colWidths.slice(0, i).reduce((sum, w) => sum + w, 0);
                // Apply indent only to first column
                const xPos = i === 0 ? baseXPos + totalIndent : baseXPos;
                // Reduce first column width by indent amount
                const cellWidth = i === 0 ? colWidths[i] - totalIndent : colWidths[i];
                
                doc.setFillColor(...bgColor);
                doc.rect(xPos, currentY, cellWidth, rowHeight, "F");

                if (isTotals) {
                    const text = cleanText(row[i] || "");
                    const textLines = doc.getTextWidth(text) > cellWidth - 4
                        ? doc.splitTextToSize(text, cellWidth - 4)
                        : [text];
                    
                    const align = i === 0 ? "left" : "right";
                    const textX = align === "left" ? xPos + 2 : xPos + cellWidth - 2;
                    const textY = currentY + (rowHeight - (lineHeight * textLines.length)) / 2 + (lineHeight - 0.5);
                    
                    doc.setTextColor(...textColor);
                    doc.setFont("helvetica", fontStyle);
                    doc.text(textLines, textX, textY, { align, maxWidth: cellWidth - 4 });
                } else {
                    const cellData = row.map((cell, j) => {
                        const adjustedWidth = j === 0 ? cellWidth : colWidths[j];
                        const text = cleanText(cell || "");
                        const textLines = doc.getTextWidth(text) > adjustedWidth - 4
                            ? doc.splitTextToSize(text, adjustedWidth - 4)
                            : [text];
                        return { textLines, cellHeight: Math.max(baseRowHeight, lineHeight * textLines.length) };
                    });

                    const align = i === 0 ? "left" : "right";
                    const textX = align === "left" ? xPos + 2 : xPos + cellWidth - 2;
                    const textY = currentY + (rowHeight - (lineHeight * cellData[i].textLines.length)) / 2 + (lineHeight - 0.5);

                    doc.setTextColor(...textColor);
                    doc.setFont("helvetica", fontStyle);
                    
                    doc.text(cellData[i].textLines, textX, textY, { align, maxWidth: cellWidth - 4 });
                }
            });

            currentY += rowHeight;
            if (!isTotals) {
                rowIndex++;
            }
        });

        // Page numbers
        const pageCount = doc.internal.getNumberOfPages();
        for (let i = 1; i <= pageCount; i++) {
            doc.setPage(i);
            doc.setFontSize(9);
            doc.setFont("helvetica", "normal");
            doc.setTextColor(0, 0, 0); // Ensure page numbers are black
            doc.text(`Page ${i} of ${pageCount}`, pageWidth / 2, pageHeight - 8, { align: "center" });
        }

        doc.save(`${window.currentReportType}_report.pdf`);
    } catch (err) {
        console.error("PDF generation error:", err);
        document.getElementById("loadingOverlay").innerHTML = `
            <div class="loading-content">
                <div class="alert alert-danger">Failed to generate PDF: ${
                    err.message || "Unknown error"
                }. Please try again.</div>
            </div>
        `;
        setTimeout(hideLoadingOverlay, 3000);
    } finally {
        pdfContent.style.display = "none";
        hideLoadingOverlay();
    }
}