
async function loadSVGAsImage(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = "Anonymous";
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

async function generatePDF() {
    if (!window.currentReportType) {
        showLoadingOverlay("No report selected. Please select a report first.");
        setTimeout(hideLoadingOverlay, 2000);
        return;
    }

    showLoadingOverlay("Generating PDF, please wait...");

    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({
        orientation: "landscape",
        unit: "mm",
        format: "a4"
    });

    const pdfContent = document.getElementById("pdfContent");
    const reportContent = document.querySelector(
        `[data-report-content="${window.currentReportType}"]`
    );
    if (!reportContent) {
        showLoadingOverlay("No report content available.");
        setTimeout(hideLoadingOverlay, 2000);
        return;
    }

    const title = reportContent.querySelector("h1").textContent;
    pdfContent.querySelector("h1").textContent = title;

    // filters
    const filterList = document.getElementById("filterList");
    filterList.innerHTML = "";
    getActiveFilters().forEach(filter => {
        const li = document.createElement("li");
        li.textContent = filter;
        li.style.fontFamily = "Helvetica, sans-serif";
        li.style.fontSize = "12px";
        filterList.appendChild(li);
    });

    // table clone
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

    // load logo
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
        const headerHeight = 8;

        let currentY = margin;

        // extract headers + data
        const headers = Array.from(table.querySelectorAll("th")).map(th =>
            th.textContent.trim()
        );
        const rows = Array.from(table.querySelectorAll("tbody tr"));
        const tableData = rows.map(row => {
            return Array.from(row.querySelectorAll("td")).map(td =>
                cleanText(td.textContent)
            );
        });
        // dynamic column widths based on header text length
        const headerLengths = headers.map(h => h.length);
        const totalLength = headerLengths.reduce((a, b) => a + b, 0);
        const colWidths = headerLengths.map(l => (l / totalLength) * usableWidth);


        // helper: draw page header
        function drawPageHeader(pageTitle, firstPage = false) {
            let y = margin;
            if (logoDataUrl) {
                const logoWidth = 30;
                const logoHeight = 30;
                doc.addImage(
                    logoDataUrl,
                    "PNG",
                    (pageWidth - logoWidth) / 2,
                    y,
                    logoWidth,
                    logoHeight
                );
                y += logoHeight + 5;
            }

            // title
            if(firstPage){
                doc.setFontSize(18);
                doc.setFont("helvetica", "bold");
                doc.text(pageTitle, pageWidth / 2, y, { align: "center" });
                y += 12;
            }
            // filters only on first page
            if (firstPage) {
                doc.setFontSize(11);
                doc.setFont("helvetica", "bold");
                
                // --- "Active Filters:" on the left
                doc.text("Active Filters:", margin, y);
                
                // --- Date Range on the right
                if (window.reportParameters.startDate && window.reportParameters.endDate) {
                    const dateLabel = `For The Period: ${window.reportParameters.startDate} to ${window.reportParameters.endDate}`;
                    doc.text(dateLabel, pageWidth - margin, y, { align: "right" });
                }
                
                y += 6;
                
                // --- List filters below
                doc.setFont("helvetica", "normal");
                getActiveFilters().forEach(filter => {
                    const textLines = doc.splitTextToSize(`• ${filter}`, usableWidth - 10);
                    doc.text(textLines, margin + 4, y);
                    y += 5 * textLines.length;
                });
                y += 8;
                
            }

            // table headers
            doc.setFontSize(10);
            doc.setFont("helvetica", "bold");
            headers.forEach((header, i) => {
                const xPos = margin + colWidths.slice(0, i).reduce((sum, w) => sum + w, 0);
                doc.setFillColor(233, 239, 247);
                doc.rect(xPos, y, colWidths[i], headerHeight, "F");

                const headerText = doc.splitTextToSize(header, colWidths[i] - 2);
                const textY = y + (headerText.length === 1 ? 6 : 4);
                doc.text(headerText, xPos + colWidths[i] / 2, textY, { align: "center" });
            });


            return y + headerHeight + 2;
        }

        // draw first page header (with filters)
        currentY = drawPageHeader(title, true);

        // render rows
        doc.setFontSize(9);
        let rowIndex = 0;
        tableData.forEach(row => {
            if (currentY > pageHeight - 20) {
                doc.addPage();
                currentY = drawPageHeader(title, false); // repeat header on new page
            }

            const rowHeight = 7;
            const bgColor =
                rowIndex % 2 === 0 ? [245, 247, 250] : [255, 255, 255];

            headers.forEach((_, i) => {
                const xPos =
                    margin +
                    colWidths.slice(0, i).reduce((sum, w) => sum + w, 0);
                doc.setFillColor(...bgColor);
                doc.rect(xPos, currentY, colWidths[i], rowHeight, "F");
                const text = cleanText(row[i] || "");
                const align = i === 0 ? "left" : "right";
                const textX =
                    align === "left"
                        ? xPos + 2
                        : xPos + colWidths[i] - 2;
                doc.text(text, textX, currentY + 5, { align });
            });

            currentY += rowHeight;
            rowIndex++;
        });

        // page numbers
        const pageCount = doc.internal.getNumberOfPages();
        for (let i = 1; i <= pageCount; i++) {
            doc.setPage(i);
            doc.setFontSize(9);
            doc.setFont("helvetica", "normal");
            doc.text(
                `Page ${i} of ${pageCount}`,
                pageWidth / 2,
                pageHeight - 8,
                { align: "center" }
            );
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

