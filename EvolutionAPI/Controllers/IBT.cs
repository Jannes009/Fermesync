using Microsoft.AspNetCore.Mvc;
using Pastel.Evolution;
using Pastel.Evolution.Common;
using System;
using System.Collections.Generic;

namespace EvolutionAPI.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class EvolutionIBTController : ControllerBase
    {
        [HttpPost("process-ibt")]
        public IActionResult ProcessIBT([FromBody] IBTRequest request)
        {
            if (request == null)
                return BadRequest(new { success = false, error = "Request body is null" });

            if (request.WarehouseFrom <= 0 || request.WarehouseTo <= 0)
                return BadRequest(new { success = false, error = "WarehouseFrom and WarehouseTo are required" });

            if (request.Lines == null || request.Lines.Count == 0)
                return BadRequest(new { success = false, error = "Lines collection cannot be empty" });

            try
            {
                // -----------------------------------
                // 1. CONNECT TO EVOLUTION DATABASE
                // -----------------------------------
                DatabaseContext.CreateCommonDBConnection("SIGMAFIN-RDS\\EVOLUTION", "SageCommon", "sa", "@Evolution", false);
                DatabaseContext.SetLicense("DE12111082", "9824607");
                DatabaseContext.CreateConnection("SIGMAFIN-RDS\\EVOLUTION", "UB_UITDRAAI_BDY", "sa", "@Evolution", false);

                // -----------------------------------
                // 2. ISSUE THE IBT
                // -----------------------------------
                var ibtIssue = new WarehouseIBT
                {
                    WarehouseFrom = new Warehouse(request.WarehouseFrom),
                    WarehouseTo = new Warehouse(request.WarehouseTo),
                    Description = request.RequestedBy
                };

                foreach (var line in request.Lines)
                {
                    var issueLine = new WarehouseIBTLine
                    {
                        InventoryItem = new InventoryItem(line.ProductId),
                        Description = line.Dispatcher,
                        Reference = line.Driver,
                        QuantityIssued = line.QtyIssued
                    };

                    ibtIssue.Detail.Add(issueLine);
                }

                ibtIssue.IssueStock();

                return Ok(new
                {
                    success = true,
                    ibtNumber = ibtIssue.Number,
                    message = "IBT issued successfully"
                });
            }
            catch (Exception ex)
            {
                return BadRequest(new { success = false, error = ex.Message });
            }
        }
    }

    // =====================================================
    // DTO MODELS
    // =====================================================

    public class IBTRequest
    {
        public int WarehouseFrom { get; set; }
        public int WarehouseTo { get; set; }
        public string? RequestedBy { get; set; }
        public string? Description { get; set; }
        public List<IBTLine> Lines { get; set; } = new();
    }

    public class IBTLine
    {
        public int ProductId { get; set; }
        public double QtyIssued { get; set; }

        // For now these will always be 0 (we only send stock, not receive)
        public double QtyReceived { get; set; } = 0;
        public double QtyDamaged { get; set; } = 0;
        public double QtyVariance { get; set; } = 0;

        public string? Dispatcher { get; set; }
        public string? Driver { get; set; }
    }
}
