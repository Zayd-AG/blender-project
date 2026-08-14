-- Rojo syncs ../shared/naming_pattern.json into AssetValidatorShared as text.
local HttpService = game:GetService("HttpService")
local shared = game:GetService("ReplicatedStorage"):WaitForChild("AssetValidatorShared")

local RuntimeConfig = {}

function RuntimeConfig.getNamingPattern(): string
	local value = (shared:FindFirstChild("naming_pattern") or shared:WaitForChild("naming_pattern.json")) :: StringValue
	return HttpService:JSONDecode(value.Value).luauPattern
end

return RuntimeConfig
