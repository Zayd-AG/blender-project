-- Import Validator Roblox Studio plugin entry point.
local AssetService = game:GetService("AssetService")
local Selection = game:GetService("Selection")

local ImportValidator = require(script.Checks.ImportValidator)
local RuntimeConfig = require(script.Shared.RuntimeConfig)

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
	320,
	180,
	260,
	140
)
local widget = plugin:CreateDockWidgetPluginGui("AssetValidatorImportValidator", widgetInfo)
widget.Title = "Import Validator"

local scanButton = Instance.new("TextButton")
scanButton.Name = "ScanSelection"
scanButton.Text = "Scan Selection"
scanButton.Size = UDim2.fromOffset(180, 36)
scanButton.Position = UDim2.fromOffset(16, 16)
scanButton.Parent = widget

button.Click:Connect(function()
	widget.Enabled = not widget.Enabled
end)

scanButton.MouseButton1Click:Connect(function()
	local function getEditableMesh(meshPart: MeshPart)
		local success, editableMesh = pcall(function()
			return AssetService:CreateEditableMeshAsync(meshPart.MeshContent)
		end)
		return if success then editableMesh else nil
	end
	local config = {
		rigType = "R15" :: "R6" | "R15",
		namingPattern = RuntimeConfig.getNamingPattern(),
		minStuds = 0.1,
		maxStuds = 100,
	}
	local selection = Selection:Get()
	local findings = ImportValidator.validate(selection, config, getEditableMesh)
	local totals = ImportValidator.summarizeMeshCounts(selection, getEditableMesh)
	print("Import Validator findings:", findings, "Mesh totals:", totals)
end)
