-- Import Validator Roblox Studio plugin entry point.
local AssetService = game:GetService("AssetService")
local Selection = game:GetService("Selection")

local ImportValidator = require(script.Checks.ImportValidator)
local RuntimeConfig = require(script.Shared.RuntimeConfig)
local SafeFixes = require(script.Fixes.SafeFixes)
local ScanReport = require(script.Reporting.ScanReport)

local toolbar = plugin:CreateToolbar("Asset Validator")
local button = toolbar:CreateButton(
	"Import Validator",
	"Open the Import Validator panel",
	"rbxassetid://4458901886"
)

local widgetInfo = DockWidgetPluginGuiInfo.new(
	Enum.InitialDockState.Right,
	false,
	false,
	360,
	460,
	260,
	140
)
local widget = plugin:CreateDockWidgetPluginGuiAsync("AssetValidatorImportValidator", widgetInfo)
widget.Title = "Import Validator"

local scanButton = Instance.new("TextButton")
scanButton.Name = "ScanSelection"
scanButton.Text = "Rescan Selection"
scanButton.Size = UDim2.fromOffset(180, 36)
scanButton.Position = UDim2.fromOffset(16, 16)
scanButton.Parent = widget

local safeFixesButton = scanButton:Clone()
safeFixesButton.Name = "ApplySafeFixes"
safeFixesButton.Text = "Apply Safe Fixes"
safeFixesButton.Position = UDim2.fromOffset(16, 60)
safeFixesButton.Parent = widget

local insertRootButton = scanButton:Clone()
insertRootButton.Name = "InsertHumanoidRootPart"
insertRootButton.Text = "Insert HumanoidRootPart"
insertRootButton.Position = UDim2.fromOffset(16, 104)
insertRootButton.Visible = false
insertRootButton.Parent = widget

local exportButton = scanButton:Clone()
exportButton.Name = "ExportResults"
exportButton.Text = "Export JSON"
exportButton.Position = UDim2.fromOffset(204, 16)
exportButton.Size = UDim2.fromOffset(100, 36)
exportButton.Parent = widget

local rigTypeButton = exportButton:Clone()
rigTypeButton.Name = "RigType"
rigTypeButton.Position = UDim2.fromOffset(204, 60)
rigTypeButton.Text = "Rig: R15"
rigTypeButton.Parent = widget

local summary = Instance.new("TextLabel")
summary.Name = "Summary"
summary.BackgroundTransparency = 1
summary.TextXAlignment = Enum.TextXAlignment.Left
summary.TextYAlignment = Enum.TextYAlignment.Top
summary.TextWrapped = true
summary.Size = UDim2.fromOffset(288, 54)
summary.Position = UDim2.fromOffset(16, 148)
summary.Text = "Select imported assets, then rescan."
summary.Parent = widget

local results = Instance.new("TextLabel")
results.Name = "Results"
results.BackgroundTransparency = 1
results.TextXAlignment = Enum.TextXAlignment.Left
results.TextYAlignment = Enum.TextYAlignment.Top
results.TextWrapped = true
results.Size = UDim2.new(1, -32, 1, -220)
results.Position = UDim2.fromOffset(16, 208)
results.Text = ""
results.Parent = widget

local exportText = Instance.new("TextBox")
exportText.Name = "ExportJson"
exportText.ClearTextOnFocus = false
exportText.MultiLine = true
exportText.TextEditable = true
exportText.TextWrapped = false
exportText.TextXAlignment = Enum.TextXAlignment.Left
exportText.TextYAlignment = Enum.TextYAlignment.Top
exportText.Size = UDim2.new(1, -32, 1, -220)
exportText.Position = UDim2.fromOffset(16, 208)
exportText.Visible = false
exportText.Parent = widget

local lastSelection = {}
local lastFindings = {}
local lastConfig = nil
local rigType: "R6" | "R15" = "R15"

local function getEditableMesh(meshPart: MeshPart)
	local success, editableMesh = pcall(function()
		return AssetService:CreateEditableMeshAsync(meshPart.MeshContent)
	end)
	return if success then editableMesh else nil
end

local function selectedModels(): { Model }
	local models, seen = {}, {}
	for _, instance in Selection:Get() do
		local model = if instance:IsA("Model") then instance else instance:FindFirstAncestorOfClass("Model")
		if model and not seen[model] then
			seen[model] = true
			table.insert(models, model)
		end
	end
	return models
end

local function scan()
	lastSelection = selectedModels()
	lastConfig = { rigType = rigType, namingPattern = RuntimeConfig.getNamingPattern(), minStuds = 0.1, maxStuds = 100 }
	lastFindings = ImportValidator.validate(lastSelection, lastConfig, getEditableMesh)
	local totals = ImportValidator.summarizeMeshCounts(lastSelection, getEditableMesh)
	local high, medium, low, needsRoot = 0, 0, 0, false
	local lines = {}
	local grouped = { high = {}, medium = {}, low = {} }
	for _, finding in lastFindings do
		if finding.severity == "high" then
			high += 1
		elseif finding.severity == "medium" then
			medium += 1
		else
			low += 1
		end
		if finding.issue == "rig_missing_part" and finding.description:find("HumanoidRootPart") then
			needsRoot = true
		end
		table.insert(grouped[finding.severity], finding.instanceName .. ": " .. finding.description)
	end
	for _, severity in { "high", "medium", "low" } do
		if #grouped[severity] > 0 then
			table.insert(lines, string.upper(severity) .. "\n" .. table.concat(grouped[severity], "\n"))
		end
	end
	local totalText = {}
	for name, count in pairs(totals) do
		table.insert(totalText, name .. " " .. count.vertices .. " vertices / " .. count.triangles .. " triangles")
	end
	summary.Text = "Rig status: " .. (high == 0 and "pass" or "needs attention") .. "\n" .. table.concat(totalText, "\n")
	results.Text = "High: " .. high .. "  Medium: " .. medium .. "  Low: " .. low .. "\n" .. table.concat(lines, "\n")
	results.Visible = true
	exportText.Visible = false
	insertRootButton.Visible = needsRoot
end

button.Click:Connect(function()
	widget.Enabled = not widget.Enabled
end)

scanButton.MouseButton1Click:Connect(function()
	scan()
end)

safeFixesButton.MouseButton1Click:Connect(function()
	if not lastConfig then
		return
	end
	local before = #lastFindings
	for _, model in lastSelection do
		SafeFixes.apply(model, lastConfig.rigType, false)
	end
	scan()
	summary.Text = "Safe fixes: " .. before .. " → " .. #lastFindings .. " findings\n" .. summary.Text
end)

insertRootButton.MouseButton1Click:Connect(function()
	if not lastConfig then
		return
	end
	local before = #lastFindings
	for _, model in lastSelection do
		SafeFixes.apply(model, lastConfig.rigType, true)
	end
	scan()
	summary.Text = "Root insertion: " .. before .. " → " .. #lastFindings .. " findings\n" .. summary.Text
end)

exportButton.MouseButton1Click:Connect(function()
	exportText.Text = ScanReport.toJson(lastSelection, lastFindings)
	exportText.Visible = true
	results.Visible = false
end)

rigTypeButton.MouseButton1Click:Connect(function()
	rigType = if rigType == "R15" then "R6" else "R15"
	rigTypeButton.Text = "Rig: " .. rigType
end)
