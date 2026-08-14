local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TestEZ = require(ReplicatedStorage.Packages.TestEZ)

local results = TestEZ.TestBootstrap:run({ script.Parent })
if results.failureCount > 0 then
	error(string.format("%d TestEZ test(s) failed", results.failureCount))
end
