using Microsoft.AspNetCore.Mvc;
using Pastel.Evolution;
using Pastel.Evolution.Common;
using System.Collections.Generic;

namespace EvolutionAPI.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class EvolutionTestController : ControllerBase
    {
        [HttpPost("submit-grv")]
        public IActionResult SubmitGRV([FromBody] GRVRequest request)
        {
            // Validate request
            if (request == null)
            {
                return BadRequest(new { success = false, error = "Request body is null" });
            }

            if (string.IsNullOrEmpty(request.PoNumber))
            {
                return BadRequest(new { success = false, error = "PoNumber is required" });
            }

            if (request.Lines == null || request.Lines.Count == 0)
            {
                return BadRequest(new { success = false, error = "Lines collection is required and cannot be empty" });
            }

            try
            {
                DatabaseContext.CreateCommonDBConnection("SIGMAFIN-RDS\\EVOLUTION", "SageCommon", "sa", "@Evolution", false);
                DatabaseContext.SetLicense("DE12111082", "9824607");
                DatabaseContext.CreateConnection("SIGMAFIN-RDS\\EVOLUTION", "UB_UITDRAAI_BDY", "sa", "@Evolution", false);

                PurchaseOrder PO = new PurchaseOrder(request.PoNumber);

                foreach (var line in request.Lines)
                {
                    foreach (OrderDetail detail in PO.Detail)
                    {
                        if (detail.InventoryItemID.ToString() == line.ProductId)
                        {
                            detail.ToProcess = (double)line.QtyReceived; // cast decimal → double
                            break;
                        }
                    }
                }

                PO.ProcessStock();

                return Ok(new { success = true });
            }
            catch (Exception ex)
            {
                return BadRequest(new { success = false, error = ex.Message });
            }
        }
    }

    // DTOs must be **outside the controller class**
    public class GRVRequest
    {
        public string PoNumber { get; set; }
        public List<GRVLine> Lines { get; set; }
    }

    public class GRVLine
    {
        public string ProductId { get; set; }
        public decimal QtyReceived { get; set; }
    }
}
