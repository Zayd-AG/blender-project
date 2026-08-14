local HttpService = game:GetService("HttpService")

local ScanReport = {}

function ScanReport.toJson(selection: { Instance }, findings): string
	local assets = {}
	for _, instance in selection do
		table.insert(assets, { object_name = instance.Name, status = "passed", findings = {} })
	end
	for _, finding in findings do
		for _, asset in assets do
			if asset.object_name == finding.instanceName then
				asset.status = "failed"
				table.insert(asset.findings, { issue = finding.issue, severity = finding.severity, description = finding.description, auto_fixable = finding.autoFixable })
			end
		end
	end
	return HttpService:JSONEncode({ generated_at = DateTime.now():ToIsoDate(), collection = "StudioSelection", assets = assets })
end

return ScanReport
