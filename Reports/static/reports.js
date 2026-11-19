window.FermeReports = {
  formatCurrency(value) {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: "ZAR", maximumFractionDigits: 2 }).format(value || 0);
  },
  formatNumber(value) {
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value || 0);
  }
};
